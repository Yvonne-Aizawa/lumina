# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time VRM avatar viewer with server-controlled animations. A FastAPI backend controls a Three.js browser frontend via WebSocket, allowing Python code to trigger character animations. Intended as the foundation for an AI chatbot with a responsive 3D character.

## Running the Project

```bash
# Setup (first time)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run server
python server.py
# Opens at http://localhost:8000
```

## Controlling Animations

```bash
# List available animations (auto-scanned from anims/ folder)
curl http://localhost:8000/api/animations

# Trigger an animation in all connected browsers
curl -X POST http://localhost:8000/api/play/Waving
```

From Python server code: `await play_animation("Waving")`

## Architecture

**`server.py`** — FastAPI server. Serves the frontend, manages WebSocket connections to browsers, broadcasts animation commands. Key functions: `play_animation(name)`, `list_animations()`, `broadcast(message)`.

**`static/index.html`** — Self-contained Three.js app. Loads a VRM model, preloads all FBX animations from the server's animation list, connects via WebSocket to receive `{"action": "play", "animation": "name"}` commands.

**Animation retargeting** — Mixamo FBX animations are converted to VRM bone space in the browser. The `loadMixamoAnimation()` function extracts world rest rotations from FBX bones and transforms keyframes using `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Adding Animations

Drop Mixamo FBX files (exported as **FBX Binary**, **Without Skin**) into the `anims/` folder and restart the server. The filename stem becomes the animation name.

## Asset Files (git-ignored)

- `*.vrm` — VRM avatar model (served from project root as `/testavi.vrm`)
- `anims/*.fbx` — Mixamo animation files
- `venv/` — Python virtual environment

## Dependencies

- **Python:** FastAPI, uvicorn (with WebSocket support)
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2
