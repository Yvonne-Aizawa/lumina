# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI chatbot with a 3D VRM avatar. FastAPI backend controls a Three.js browser frontend via WebSocket. The LLM can trigger character animations, manage persistent memories, and use external tools via MCP servers. A background heartbeat system lets the AI proactively reach out to the user.

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

## Architecture

**`server.py`** — Thin launcher. Imports the FastAPI app from `app/server.py` and runs uvicorn.

**`app/server.py`** — FastAPI server. Manages app lifecycle (MCP startup/shutdown, heartbeat task), WebSocket connections to browsers, REST API endpoints. Routes: `/` (frontend), `/api/chat` (POST), `/api/animations` (GET), `/api/play/{name}` (POST), `/api/chat/clear` (POST), `/ws` (WebSocket).

**`app/chat.py`** — Chat handler. Manages conversation history, LLM calls via OpenAI SDK, and tool execution loop (up to `MAX_TOOL_ROUNDS=10` iterations). Built-in tools: `play_animation`, `memory_create`, `memory_read`, `memory_edit`, `memory_delete`, `memory_list`. Also routes to MCP tools. The system prompt is built from `state/soul/` markdown files (excluding `heartbeat.md`), loaded once at init. Has a separate `heartbeat()` method for background prompts. An `asyncio.Lock` protects `_messages` for concurrency safety.

**`app/mcp_manager.py`** — MCP client manager. Connects to configured MCP servers via stdio on startup, discovers their tools, converts tool schemas to OpenAI function-calling format, and routes tool calls to the correct server session.

### Frontend (static/)

The frontend is split into ES modules served via FastAPI's StaticFiles mount:

- **`static/index.html`** — Minimal HTML shell with import map for CDN dependencies and links to CSS/JS.
- **`static/css/style.css`** — All styles.
- **`static/js/app.js`** — Entry point. Loads VRM, preloads animations, starts render loop.
- **`static/js/scene.js`** — Three.js scene, camera, renderer, lighting, controls.
- **`static/js/animations.js`** — Mixamo FBX-to-VRM retargeting, bone mapping, playback. Exports shared state (`animationClips`, `mixer` via `setMixer`).
- **`static/js/websocket.js`** — WebSocket connection with auto-reconnect. Handles `play` (animation) and `chat` (heartbeat messages) actions.
- **`static/js/chat.js`** — Chat UI. Exports `addMessage` (used by websocket.js for heartbeat) and `initChat`.

## Key Data Flow

```
Browser chat input → POST /api/chat → ChatHandler.send_message()
  → LLM (OpenAI-compatible API) with tools
  → tool calls (animation/memory/MCP) executed in loop
  → final text response returned to browser
  → animations triggered via WebSocket broadcast to all clients
```

### Heartbeat Flow

```
heartbeat_loop() runs every HEARTBEAT_INTERVAL (600s)
  → skips if user interacted within HEARTBEAT_IDLE_THRESHOLD (1200s)
  → skips if already waiting for user to respond
  → ChatHandler.heartbeat() makes isolated LLM call with state/soul/heartbeat.md prompt
  → response broadcast via WebSocket {"action": "chat", "content": "..."}
  → heartbeat pauses until user sends next message
```

The heartbeat uses a completely separate LLM call — no shared conversation history. It only gets the system prompt + heartbeat prompt.

## Configuration

**`config.json`** — LLM endpoint and MCP servers. Supports both `mcp_servers` and `mcpServers` (LM Studio format) keys.

**`state/soul/*.md`** — Personality/identity files loaded alphabetically into the system prompt at startup. `heartbeat.md` is excluded from the system prompt and used only by the heartbeat system. Restart server to pick up changes.

**`state/memories/*.md`** — Persistent memory files created/managed by the LLM via tool calls. Filenames are sanitized to prevent path traversal.

## Adding Animations

Drop Mixamo FBX files (exported as **FBX Binary**, **Without Skin**) into `assets/anims/` and restart. The filename stem becomes the animation name.

## Animation Retargeting

Mixamo FBX animations are retargeted to VRM in the browser. `loadMixamoAnimation()` in `static/js/animations.js` extracts world rest rotations from FBX bones and transforms keyframes: `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Git-ignored Assets

`assets/`, `state/`, `venv/`, `__pycache__/`

## Dependencies

- **Python:** fastapi, uvicorn[standard], openai, mcp
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2
