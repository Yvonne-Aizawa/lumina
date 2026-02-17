"""Animation and background route handlers."""

from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..broadcast import list_animations, list_backgrounds, play_animation

router = APIRouter()


@router.get("/api/animations", dependencies=[Depends(require_auth)])
async def get_animations():
    return {"animations": list_animations()}


@router.get("/api/backgrounds", dependencies=[Depends(require_auth)])
async def get_backgrounds():
    return {"backgrounds": list_backgrounds()}


@router.post("/api/play/{animation_name}", dependencies=[Depends(require_auth)])
async def api_play(animation_name: str):
    anims = list_animations()
    if animation_name not in anims:
        return {"error": f"Unknown animation: {animation_name}", "available": anims}
    await play_animation(animation_name)
    return {"status": "ok", "animation": animation_name}
