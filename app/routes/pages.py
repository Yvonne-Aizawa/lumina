"""Page-serving and static asset route handlers."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .. import config as _config
from ..broadcast import _background_filename
from ..config import PROJECT_DIR

router = APIRouter()


@router.get("/")
async def index():
    return FileResponse(PROJECT_DIR / "static" / "index.html")


@router.get("/api/config/background")
async def api_config_background():
    from ..server import _default_background

    bg = _default_background
    if bg and not bg.startswith("#"):
        bg = _background_filename(bg)
    return {"background": bg}


@router.get("/memory")
async def memory_page():
    return FileResponse(PROJECT_DIR / "static" / "memory.html")


@router.get("/avatar.vrm")
async def serve_vrm():
    return FileResponse(_config.MODELS_DIR / _config.VRM_MODEL)
