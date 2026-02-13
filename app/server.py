"""FastAPI application — routes, lifespan, and static mounts."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
from .stt import (
    init_stt,
    init_wakeword,
    stt_enabled,
    stt_model,
    transcribe,
    wakeword_enabled,
    wakeword_keyword,
)
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
    init_tts(config.tts)
    await init_stt(config.stt)
    init_wakeword(config.wakeword)
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


# --- Routes ---


@app.get("/")
async def index():
    return FileResponse(PROJECT_DIR / "static" / "index.html")


@app.get("/api/animations")
async def get_animations():
    return {"animations": list_animations()}


@app.post("/api/play/{animation_name}")
async def api_play(animation_name: str):
    anims = list_animations()
    if animation_name not in anims:
        return {"error": f"Unknown animation: {animation_name}", "available": anims}
    await play_animation(animation_name)
    return {"status": "ok", "animation": animation_name}


class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
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


@app.post("/api/chat/clear")
async def api_chat_clear():
    if chat_handler:
        chat_handler.clear_history()
    return {"status": "ok"}


@app.get("/api/stt/status")
async def api_stt_status():
    from .stt import stt_enabled, wakeword_enabled, wakeword_keyword

    return {
        "enabled": stt_enabled,
        "wakeword": wakeword_keyword,
        "wakeword_enabled": wakeword_enabled,
    }


@app.post("/api/transcribe")
async def api_transcribe(file: UploadFile):
    from .stt import stt_enabled, stt_model

    if not stt_enabled or stt_model is None:
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
    connected_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(ws)


# Serve VRM model file
@app.get("/testavi.vrm")
async def serve_vrm():
    return FileResponse(MODELS_DIR / "testavi.vrm")


# Serve animation files and static assets
app.mount("/anims", StaticFiles(directory=str(ANIMS_DIR)), name="anims")
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")
