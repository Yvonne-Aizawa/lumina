"""WebSocket route handler."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import wakeword
from ..auth import require_ws_auth
from ..broadcast import connected_clients

router = APIRouter()


@router.websocket("/ws")
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
