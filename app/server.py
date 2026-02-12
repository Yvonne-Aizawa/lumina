import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

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

# --- Global state ---

connected_clients: list[WebSocket] = []
mcp_manager: MCPManager | None = None
chat_handler: ChatHandler | None = None


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"llm": {}, "system_prompt": "", "mcp_servers": {}}


# --- App lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_manager, chat_handler

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
    )

    log.info(f"Available animations: {list_animations()}")
    log.info(
        f"MCP tools: {[t['function']['name'] for t in mcp_manager.get_openai_tools()]}"
    )

    yield

    # Shutdown
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
    if chat_handler is None:
        return {"error": "Chat not initialized"}
    try:
        response = await chat_handler.send_message(req.message)
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
