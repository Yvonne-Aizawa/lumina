"""WebSocket client management and broadcasting."""

import json
import logging

from fastapi import WebSocket

from . import config as _config

log = logging.getLogger(__name__)

connected_clients: list[WebSocket] = []


async def broadcast(message: dict):
    """Send a JSON message to all connected browser clients."""
    data = json.dumps(message)
    for ws in list(connected_clients):
        try:
            await ws.send_text(data)
        except Exception:
            connected_clients.remove(ws)


def list_animations() -> list[str]:
    """Return names of available animations (FBX files in anims/)."""
    if not _config.ANIMS_DIR.exists():
        return []
    return sorted(p.stem for p in _config.ANIMS_DIR.glob("*.fbx"))


async def play_animation(name: str):
    """Send a play command to all connected browsers."""
    await broadcast({"action": "play", "animation": name})


async def notify_tool_call(name: str, arguments: dict):
    """Broadcast a tool call notification to all connected browsers."""
    await broadcast({"action": "tool_call", "name": name, "arguments": arguments})
