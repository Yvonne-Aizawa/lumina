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

No tests or linting are configured.

## Architecture

**`server.py`** — Thin launcher. Imports the FastAPI app from `app/server.py` and runs uvicorn.

**`app/server.py`** — FastAPI server. Manages app lifecycle (MCP startup/shutdown, heartbeat task), WebSocket connections to browsers, REST API endpoints. Routes: `/` (frontend), `/api/chat` (POST), `/api/animations` (GET), `/api/play/{name}` (POST), `/api/chat/clear` (POST), `/ws` (WebSocket).

**`app/chat.py`** — Chat handler. Manages conversation history, LLM calls via OpenAI SDK, and tool execution loop (up to `MAX_TOOL_ROUNDS=10` iterations). Built-in tools: `play_animation`, `memory_create/read/edit/delete/list`, `state_set/get/list/check_time`. Also routes to MCP tools. The system prompt is built from `state/soul/` markdown files (excluding `heartbeat.md`), loaded once at init. Has a separate `heartbeat()` method for background prompts. An `asyncio.Lock` protects `_messages` for concurrency safety.

**`app/mcp_manager.py`** — MCP client manager. Connects to configured MCP servers via stdio on startup, discovers their tools, converts tool schemas to OpenAI function-calling format, and routes tool calls to the correct server session.

**`static/`** — Frontend ES modules served via FastAPI's StaticFiles mount. `app.js` is the entry point (loads VRM, preloads animations, starts render loop). `animations.js` handles Mixamo FBX-to-VRM retargeting. `websocket.js` handles auto-reconnecting WebSocket for animation playback and heartbeat messages. `chat.js` manages the chat UI.

## Key Data Flow

```
Browser chat input → POST /api/chat → ChatHandler.send_message()
  → LLM (OpenAI-compatible API) with tools
  → tool calls (animation/memory/state/MCP) executed in loop
  → final text response returned to browser
  → animations triggered via WebSocket broadcast to all clients
```

### Heartbeat Flow

```
heartbeat_loop() runs every heartbeat.interval seconds
  → skips if user interacted within heartbeat.idle_threshold
  → skips if already waiting for user to respond
  → ChatHandler.heartbeat() makes isolated LLM call with state/soul/heartbeat.md prompt
  → response broadcast via WebSocket {"action": "chat", "content": "..."}
  → heartbeat pauses until user sends next message
```

The heartbeat uses a completely separate LLM call — no shared conversation history. It only gets the system prompt + heartbeat prompt.

## Configuration

**`config.json`** (git-ignored) — Main configuration file:

```jsonc
{
  "llm": {
    "base_url": "http://localhost:1234/v1",  // OpenAI-compatible endpoint
    "api_key": "...",
    "model": "model-name"
  },
  "tts": {                          // Optional: GPT-SoVITS text-to-speech
    "enabled": false,
    "base_url": "http://localhost:9880",
    "ref_audio_path": "/path/to/reference.wav",
    "prompt_text": "...",
    "prompt_lang": "en",
    "text_lang": "en"
  },
  "heartbeat": {                     // Optional: proactive messages
    "enabled": false,
    "interval": 600,                 // seconds between heartbeat checks
    "idle_threshold": 1200           // seconds of user inactivity before triggering
  },
  "mcpServers": {                    // Optional: MCP tool servers
    "server-name": {
      "command": "...",
      "args": [],
      "env": {}
    }
  }
}
```

**`state/soul/*.md`** — Personality/identity files loaded alphabetically into the system prompt at startup. `heartbeat.md` is excluded from the system prompt and used only by the heartbeat system. Restart server to pick up changes.

**`state/memories/*.md`** — Persistent memory files created/managed by the LLM via tool calls. Filenames are sanitized to prevent path traversal.

**`state/state.json`** — Persistent key-value state store managed by the LLM via `state_*` tools.

## Adding Animations

Drop Mixamo FBX files (exported as **FBX Binary**, **Without Skin**) into `assets/anims/` and restart. The filename stem becomes the animation name. VRM model files go in `assets/models/`.

## Animation Retargeting

Mixamo FBX animations are retargeted to VRM in the browser. `loadMixamoAnimation()` in `static/js/animations.js` extracts world rest rotations from FBX bones and transforms keyframes: `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Git-ignored Assets

`assets/`, `state/`, `venv/`, `__pycache__/`, `config.json`

## Dependencies

- **Python:** fastapi, uvicorn[standard], openai, mcp, httpx
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2
