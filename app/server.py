"""FastAPI application — routes, lifespan, and static mounts."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config as _config
from . import wakeword
from .auth import init_auth, require_auth, require_ws_auth
from .auth import router as auth_router
from .broadcast import (
    _background_filename,
    broadcast,
    connected_clients,
    list_animations,
    list_backgrounds,
    notify_tool_call,
    play_animation,
    set_background,
    set_expression,
)
from .chat import ChatHandler
from .config import PROJECT_DIR, Config, load_config
from .emotion import detect_emotion, init_emotion
from .heartbeat import record_user_interaction, start_heartbeat
from .mcp_manager import MCPManager
from .stt import init_stt, transcribe
from .stt import is_enabled as stt_is_enabled
from .tools import init_vector_search, start_servers_from_manifest
from .tools._vector import get_collection
from .tts import init_tts, synthesize_and_broadcast

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Global state ---

mcp_manager: MCPManager | None = None
chat_handler: ChatHandler | None = None
heartbeat_task: asyncio.Task | None = None
_default_background: str | None = None


# --- App lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_manager, chat_handler, heartbeat_task, _default_background

    config = load_config()
    _default_background = config.background

    # Start MCP manager
    mcp_manager = MCPManager()
    await mcp_manager.start(config.mcp_servers)

    # Create chat handler
    backgrounds = list_backgrounds()
    chat_handler = ChatHandler(
        llm_config=config.llm,
        mcp_manager=mcp_manager,
        animation_names=list_animations(),
        play_animation_fn=play_animation,
        notify_tool_call_fn=notify_tool_call,
        bash_enabled=config.bash.enabled,
        background_names=backgrounds,
        set_background_fn=set_background,
        builtin_tools_config=config.builtin_tools,
    )

    # log.info(f"Available animations: {list_animations()}")
    # log.info(f"Available backgrounds: {backgrounds}")
    log.info(
        f"MCP tools: {[t['function']['name'] for t in mcp_manager.get_openai_tools()]}"
    )
    log.info(
        f"Brave Search: {'enabled' if config.builtin_tools.web_search.brave_api_key else 'disabled'}"
    )

    # Initialise subsystems
    init_auth(config.auth)
    init_tts(config.tts)
    await init_stt(config.stt)
    await wakeword.init_wakeword(config.wakeword)
    init_vector_search(config.builtin_tools.vector_search)
    init_emotion(config.emotion)
    if config.builtin_tools.mcp_servers:
        await start_servers_from_manifest(mcp_manager)
    heartbeat_task = start_heartbeat(config.heartbeat, chat_handler)

    # Mount asset dirs after config is loaded (assets_dir may have changed)
    app.mount("/anims", StaticFiles(directory=str(_config.ANIMS_DIR)), name="anims")
    if _config.BACKGROUNDS_DIR.exists():
        app.mount(
            "/backgrounds",
            StaticFiles(directory=str(_config.BACKGROUNDS_DIR)),
            name="backgrounds",
        )

    yield

    # Shutdown
    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
    await mcp_manager.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)


# --- Routes ---


@app.get("/")
async def index():
    return FileResponse(PROJECT_DIR / "static" / "index.html")


@app.get("/api/config/background")
async def api_config_background():
    bg = _default_background
    # Resolve image stem to full filename if it's not a color
    if bg and not bg.startswith("#"):
        bg = _background_filename(bg)
    return {"background": bg}


@app.get("/api/animations", dependencies=[Depends(require_auth)])
async def get_animations():
    return {"animations": list_animations()}


@app.get("/api/backgrounds", dependencies=[Depends(require_auth)])
async def get_backgrounds():
    return {"backgrounds": list_backgrounds()}


@app.post("/api/play/{animation_name}", dependencies=[Depends(require_auth)])
async def api_play(animation_name: str):
    anims = list_animations()
    if animation_name not in anims:
        return {"error": f"Unknown animation: {animation_name}", "available": anims}
    await play_animation(animation_name)
    return {"status": "ok", "animation": animation_name}


class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat", dependencies=[Depends(require_auth)])
async def api_chat(req: ChatRequest):
    record_user_interaction()
    if chat_handler is None:
        return {"error": "Chat not initialized"}
    try:
        response = await chat_handler.send_message(req.message)
        if response:
            expression = await detect_emotion(response)
            if expression:
                await set_expression(expression)
            await synthesize_and_broadcast(response)
        return {"response": response}
    except Exception as e:
        log.exception("Chat error")
        return {"error": str(e)}


@app.post("/api/chat/clear", dependencies=[Depends(require_auth)])
async def api_chat_clear():
    if chat_handler:
        chat_handler.clear_history()
    return {"status": "ok"}


@app.get("/api/chats", dependencies=[Depends(require_auth)])
async def api_chats():
    if chat_handler is None:
        return {"sessions": []}
    return {
        "sessions": chat_handler.list_sessions(),
        "current": chat_handler.current_session_id,
    }


class ChatLoadRequest(BaseModel):
    id: str


@app.post("/api/chats/new", dependencies=[Depends(require_auth)])
async def api_chats_new():
    if chat_handler is None:
        return {"error": "Chat not initialized"}
    chat_handler.clear_history()
    return {"status": "ok", "id": chat_handler.current_session_id}


@app.post("/api/chats/load", dependencies=[Depends(require_auth)])
async def api_chats_load(req: ChatLoadRequest):
    if chat_handler is None:
        return {"error": "Chat not initialized"}
    try:
        messages = chat_handler.load_session(req.id)
        return {"status": "ok", "id": req.id, "messages": messages}
    except FileNotFoundError as e:
        return {"error": str(e)}


@app.get("/api/stt/status", dependencies=[Depends(require_auth)])
async def api_stt_status():
    return {
        "enabled": stt_is_enabled(),
        "wakeword": wakeword.get_keyword(),
        "wakeword_enabled": wakeword.is_enabled(),
        "wakeword_auto_start": wakeword.is_auto_start(),
    }


@app.post("/api/transcribe", dependencies=[Depends(require_auth)])
async def api_transcribe(file: UploadFile):
    if not stt_is_enabled():
        return {"error": "STT not enabled"}
    try:
        audio_bytes = await file.read()
        text = await transcribe(audio_bytes)
        return {"text": text}
    except Exception as e:
        log.exception("STT transcription error")
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    if not await require_ws_auth(ws):
        await ws.close(code=4001, reason="Unauthorized")
        return
    connected_clients.append(ws)
    client_id = id(ws)
    wakeword.register_client(client_id)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                result = wakeword.process_audio(client_id, msg["bytes"])
                if result:
                    await ws.send_json({"action": "wakeword_detected", **result})
            elif msg.get("text"):
                import json as _json

                try:
                    data = _json.loads(msg["text"])
                    action = data.get("action")
                    if action == "wakeword_pause":
                        wakeword.pause(client_id)
                    elif action == "wakeword_resume":
                        wakeword.resume(client_id)
                except (ValueError, AttributeError):
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        wakeword.remove_client(client_id)
        if ws in connected_clients:
            connected_clients.remove(ws)


# --- Memory manager page ---


@app.get("/memory")
async def memory_page():
    return FileResponse(PROJECT_DIR / "static" / "memory.html")


@app.get("/api/vector", dependencies=[Depends(require_auth)])
async def api_vector_list():
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    result = col.get(include=["documents", "metadatas"])
    entries = []
    for i, eid in enumerate(result["ids"]):
        entries.append(
            {
                "id": eid,
                "content": result["documents"][i] if result["documents"] else "",
                "metadata": result["metadatas"][i] if result["metadatas"] else {},
            }
        )
    return {"entries": entries}


@app.get("/api/vector/{entry_id}", dependencies=[Depends(require_auth)])
async def api_vector_get(entry_id: str):
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    result = col.get(ids=[entry_id], include=["documents", "metadatas"])
    if not result["ids"]:
        return {"error": f"Entry '{entry_id}' not found."}
    return {
        "id": result["ids"][0],
        "content": result["documents"][0] if result["documents"] else "",
        "metadata": result["metadatas"][0] if result["metadatas"] else {},
    }


class VectorUpdateRequest(BaseModel):
    content: str
    metadata: dict | None = None


@app.put("/api/vector/{entry_id}", dependencies=[Depends(require_auth)])
async def api_vector_update(entry_id: str, req: VectorUpdateRequest):
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    existing = col.get(ids=[entry_id])
    if not existing["ids"]:
        return {"error": f"Entry '{entry_id}' not found."}
    metadata = req.metadata if req.metadata else None
    col.upsert(
        ids=[entry_id],
        documents=[req.content],
        metadatas=[metadata] if metadata else None,
    )
    return {"status": "ok", "id": entry_id}


@app.delete("/api/vector/{entry_id}", dependencies=[Depends(require_auth)])
async def api_vector_delete(entry_id: str):
    col = get_collection()
    if col is None:
        return {"error": "Vector search not initialized."}
    col.delete(ids=[entry_id])
    return {"status": "ok", "id": entry_id}


# Serve VRM model file
@app.get("/avatar.vrm")
async def serve_vrm():
    return FileResponse(_config.MODELS_DIR / _config.VRM_MODEL)


# Serve static assets (anims mount is in lifespan after config loads)
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")
