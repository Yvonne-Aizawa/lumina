"""FastAPI application — lifespan, middleware, and router mounts."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from . import config as _config
from . import wakeword
from .auth import init_auth
from .auth import router as auth_router
from .broadcast import (
    list_animations,
    list_backgrounds,
    notify_tool_call,
    play_animation,
    set_background,
)
from .chat import ChatHandler
from .config import PROJECT_DIR, load_config
from .emotion import init_emotion
from .heartbeat import start_heartbeat
from .mcp_manager import MCPManager
from .routes.animations import router as animations_router
from .routes.chat import router as chat_router
from .routes.pages import router as pages_router
from .routes.stt import router as stt_router
from .routes.vector import router as vector_router
from .routes.websocket import router as ws_router
from .stt import init_stt
from .tools import init_vector_search, start_servers_from_manifest
from .tts import init_tts

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


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# --- Routers ---

app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(chat_router)
app.include_router(animations_router)
app.include_router(stt_router)
app.include_router(vector_router)
app.include_router(ws_router)

# --- Static files ---

app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")
