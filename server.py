from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
ANIMS_DIR = BASE_DIR / "anims"

app = FastAPI()

# --- WebSocket connection manager ---

connected_clients: list[WebSocket] = []


async def broadcast(message: dict):
    """Send a JSON message to all connected browser clients."""
    import json

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
    return FileResponse(BASE_DIR / "static" / "index.html")


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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        while True:
            # Keep connection alive, handle any messages from browser
            data = await ws.receive_text()
            # Could handle browser -> server messages here in the future
    except WebSocketDisconnect:
        connected_clients.remove(ws)


# Serve VRM model file
@app.get("/testavi.vrm")
async def serve_vrm():
    return FileResponse(BASE_DIR / "models/testavi.vrm")


# Serve animation files and static assets
app.mount("/anims", StaticFiles(directory=str(ANIMS_DIR)), name="anims")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

if __name__ == "__main__":
    print(f"Available animations: {list_animations()}")
    print("Control animations via:")
    print("  curl http://localhost:8000/api/animations")
    print("  curl -X POST http://localhost:8000/api/play/Waving")
    uvicorn.run(app, host="0.0.0.0", port=8000)
