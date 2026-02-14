"""Authentication middleware and routes."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel

if TYPE_CHECKING:
    from .config import AuthConfig

log = logging.getLogger(__name__)

_enabled: bool = False
_api_key: str = ""

router = APIRouter(prefix="/api/auth", tags=["auth"])


def init_auth(config: AuthConfig):
    """Initialize auth settings from config."""
    global _enabled, _api_key
    _enabled = config.enabled
    _api_key = config.api_key
    if _enabled:
        if not _api_key:
            log.warning(
                "Auth enabled but no api_key set — all requests will be rejected"
            )
        else:
            log.info("Authentication enabled")


def is_enabled() -> bool:
    return _enabled


def verify_token(token: str) -> bool:
    """Check if a token matches the configured API key."""
    if not _enabled:
        return True
    return hmac.compare_digest(token, _api_key)


async def require_auth(request: Request):
    """FastAPI dependency that enforces authentication on routes."""
    if not _enabled:
        return
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if verify_token(token):
            return
    raise HTTPException(status_code=401, detail="Unauthorized")


async def require_ws_auth(websocket: WebSocket) -> bool:
    """Check WebSocket auth from query param. Returns True if authorized."""
    if not _enabled:
        return True
    token = websocket.query_params.get("token", "")
    return verify_token(token)


class LoginRequest(BaseModel):
    api_key: str


@router.post("/login")
async def login(req: LoginRequest):
    if not _enabled:
        return {"token": "", "auth_enabled": False}
    if not hmac.compare_digest(req.api_key, _api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {"token": _api_key}


@router.get("/check")
async def check_auth(request: Request):
    if not _enabled:
        return {"authenticated": True, "auth_enabled": False}
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if verify_token(token):
            return {"authenticated": True}
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/status")
async def auth_status():
    """Public endpoint — tells the frontend whether auth is enabled."""
    return {"auth_enabled": _enabled}
