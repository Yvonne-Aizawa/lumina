import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .chat import ChatHandler
from .mcp_manager import MCPManager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent.parent
ANIMS_DIR = PROJECT_DIR / "anims"
CONFIG_PATH = PROJECT_DIR / "config.json"
HEARTBEAT_INTERVAL_DEFAULT = 600  # seconds (10 minutes)
HEARTBEAT_IDLE_DEFAULT = 1200  # seconds (20 minutes)

# --- Global state ---

connected_clients: list[WebSocket] = []
mcp_manager: MCPManager | None = None
chat_handler: ChatHandler | None = None
heartbeat_task: asyncio.Task | None = None
heartbeat_interval: int = HEARTBEAT_INTERVAL_DEFAULT
heartbeat_idle_threshold: int = HEARTBEAT_IDLE_DEFAULT
last_user_interaction: float = 0.0
heartbeat_waiting_for_user: bool = False
tts_config: dict | None = None


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"llm": {}, "system_prompt": "", "mcp_servers": {}}


# --- App lifecycle ---


async def heartbeat_loop():
    """Periodically prompt the LLM via heartbeat when the user has been idle."""
    global heartbeat_waiting_for_user
    while True:
        await asyncio.sleep(heartbeat_interval)
        if chat_handler is None:
            continue
        if heartbeat_waiting_for_user:
            continue
        idle_time = time.monotonic() - last_user_interaction
        if idle_time < heartbeat_idle_threshold:
            continue
        try:
            await broadcast({"action": "heartbeat", "status": "start"})
            sent = await chat_handler.heartbeat()
            await broadcast({"action": "heartbeat", "status": "end"})
            if sent:
                for text in sent:
                    log.info(f"Heartbeat message: {text[:100]}")
                    await broadcast({"action": "chat", "content": text})
                    await synthesize_and_broadcast(text)
                heartbeat_waiting_for_user = True
        except Exception:
            await broadcast({"action": "heartbeat", "status": "end"})
            log.exception("Heartbeat loop error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_manager, chat_handler, heartbeat_task
    global heartbeat_interval, heartbeat_idle_threshold, tts_config

    config = load_config()

    # Start MCP manager
    mcp_manager = MCPManager()
    # Support both "mcp_servers" and "mcpServers" (LM Studio format)
    mcp_servers = config.get("mcp_servers") or config.get("mcpServers") or {}
    await mcp_manager.start(mcp_servers)

    # Create chat handler
    chat_handler = ChatHandler(
        llm_config=config.get("llm", {}),
        mcp_manager=mcp_manager,
        animation_names=list_animations(),
        play_animation_fn=play_animation,
        notify_tool_call_fn=notify_tool_call,
    )

    log.info(f"Available animations: {list_animations()}")
    log.info(
        f"MCP tools: {[t['function']['name'] for t in mcp_manager.get_openai_tools()]}"
    )

    # Load TTS config
    tts_cfg = config.get("tts", {})
    if tts_cfg.get("enabled"):
        tts_config = tts_cfg
        log.info(f"TTS enabled (server: {tts_cfg['base_url']})")

    # Start background heartbeat if enabled
    hb_config = config.get("heartbeat", {})
    if hb_config.get("enabled", False):
        heartbeat_interval = hb_config.get("interval", HEARTBEAT_INTERVAL_DEFAULT)
        heartbeat_idle_threshold = hb_config.get(
            "idle_threshold", HEARTBEAT_IDLE_DEFAULT
        )
        heartbeat_task = asyncio.create_task(heartbeat_loop())
        log.info(
            f"Heartbeat enabled (interval={heartbeat_interval}s, idle_threshold={heartbeat_idle_threshold}s)"
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


# --- WebSocket ---


async def broadcast(message: dict):
    """Send a JSON message to all connected browser clients."""
    data = json.dumps(message)
    for ws in list(connected_clients):
        try:
            await ws.send_text(data)
        except Exception:
            connected_clients.remove(ws)


# --- Animation helpers ---


def list_animations() -> list[str]:
    """Return names of available animations (FBX files in anims/)."""
    if not ANIMS_DIR.exists():
        return []
    return sorted(p.stem for p in ANIMS_DIR.glob("*.fbx"))


async def play_animation(name: str):
    """Send a play command to all connected browsers."""
    await broadcast({"action": "play", "animation": name})


async def notify_tool_call(name: str, arguments: dict):
    """Broadcast a tool call notification to all connected browsers."""
    await broadcast({"action": "tool_call", "name": name, "arguments": arguments})


async def synthesize_and_broadcast(text: str):
    """Call GPT-SoVITS to synthesize speech and broadcast audio to all clients."""
    if not tts_config or not tts_config.get("enabled"):
        return
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{tts_config['base_url']}/tts",
                json={
                    "text": text,
                    "text_lang": tts_config.get("text_lang", "en"),
                    "ref_audio_path": tts_config.get("ref_audio_path", ""),
                    "prompt_text": tts_config.get("prompt_text", ""),
                    "prompt_lang": tts_config.get("prompt_lang", "en"),
                },
            )
            if resp.status_code == 200:
                audio_b64 = base64.b64encode(resp.content).decode("ascii")
                await broadcast({"action": "audio", "data": audio_b64})
            else:
                log.warning(f"TTS failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        log.exception("TTS synthesis error")


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
    global last_user_interaction, heartbeat_waiting_for_user
    last_user_interaction = time.monotonic()
    heartbeat_waiting_for_user = False
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
    return FileResponse(PROJECT_DIR / "models/testavi.vrm")


# Serve animation files and static assets
app.mount("/anims", StaticFiles(directory=str(ANIMS_DIR)), name="anims")
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")
