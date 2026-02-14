"""FastAPI application — routes, lifespan, and static mounts."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import wakeword
from .auth import init_auth, require_auth, require_ws_auth
from .auth import router as auth_router
from .broadcast import (
    broadcast,
    connected_clients,
    list_animations,
    notify_tool_call,
    play_animation,
)
from .chat import ChatHandler
from .config import ANIMS_DIR, MODELS_DIR, PROJECT_DIR, Config, load_config
from .heartbeat import record_user_interaction, start_heartbeat
from .mcp_manager import MCPManager
from .stt import init_stt, transcribe
from .stt import is_enabled as stt_is_enabled
from .tts import init_tts, synthesize_and_broadcast

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Global state ---

mcp_manager: MCPManager | None = None
chat_handler: ChatHandler | None = None
heartbeat_task: asyncio.Task | None = None


# --- App lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_manager, chat_handler, heartbeat_task

    config = load_config()

    # Start MCP manager
    mcp_manager = MCPManager()
    await mcp_manager.start(config.mcp_servers)

    # Create chat handler
    chat_handler = ChatHandler(
        llm_config=config.llm,
        mcp_manager=mcp_manager,
        animation_names=list_animations(),
        play_animation_fn=play_animation,
        notify_tool_call_fn=notify_tool_call,
        brave_api_key=config.brave.api_key if config.brave.enabled else None,
        bash_enabled=config.bash.enabled,
    )

    log.info(f"Available animations: {list_animations()}")
    log.info(
        f"MCP tools: {[t['function']['name'] for t in mcp_manager.get_openai_tools()]}"
    )
    log.info(f"Brave Search: {'enabled' if config.brave.enabled else 'disabled'}")

    # Initialise subsystems
    init_auth(config.auth)
    init_tts(config.tts)
    await init_stt(config.stt)
    await wakeword.init_wakeword(config.wakeword)
    heartbeat_task = start_heartbeat(config.heartbeat, chat_handler)

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


@app.get("/api/animations", dependencies=[Depends(require_auth)])
async def get_animations():
    return {"animations": list_animations()}


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


# Serve VRM model file
@app.get("/avatar.vrm")
async def serve_vrm():
    return FileResponse(MODELS_DIR / "avatar.vrm")


# Serve animation files and static assets
app.mount("/anims", StaticFiles(directory=str(ANIMS_DIR)), name="anims")
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")
