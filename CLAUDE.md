# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI chatbot with a 3D VRM avatar. FastAPI backend controls a Three.js browser frontend via WebSocket. The LLM can trigger character animations, manage persistent memories, and use external tools via MCP servers. Features include TTS (GPT-SoVITS), STT (faster-whisper), server-side wake word detection (openwakeword), and a background heartbeat system for proactive AI messages.

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

**`app/server.py`** — FastAPI app, lifespan orchestrator, and route handlers. The lifespan function calls init functions from the subsystem modules below. Routes: `/` (frontend), `/api/chat` (POST), `/api/animations` (GET), `/api/play/{name}` (POST), `/api/chat/clear` (POST), `/api/chats` (GET), `/api/chats/new` (POST), `/api/chats/load` (POST), `/api/stt/status` (GET), `/api/transcribe` (POST), `/ws` (WebSocket). Auth routes are mounted from `app/auth.py`. All API routes use `Depends(require_auth)`; WebSocket checks token via query param; static files and `/`, `/api/auth/*` are unprotected.

**`app/config.py`** — Path constants (`PROJECT_DIR`, `ASSETS_DIR`, `ANIMS_DIR`, `MODELS_DIR`, `CONFIG_PATH`) and `load_config()`.

**`app/broadcast.py`** — WebSocket client list and `broadcast()` for sending JSON to all connected browsers. Also contains animation helpers: `list_animations()`, `play_animation()`, `notify_tool_call()`.

**`app/tts.py`** — TTS client. `init_tts(config)` loads settings, `synthesize_and_broadcast(text)` calls GPT-SoVITS and broadcasts base64 audio via WebSocket.

**`app/stt.py`** — STT model. `init_stt(config)` loads faster-whisper in a thread executor (with NVIDIA CUDA libraries pre-loaded via `ctypes`). `transcribe(audio_bytes)` runs transcription in a thread executor. `is_enabled()` getter returns live state (do not import the `stt_enabled` variable directly — it's set after import time).

**`app/wakeword.py`** — Server-side wake word detection using openwakeword. `init_wakeword(config)` loads the ONNX keyword model at startup. Browser streams 16kHz Int16 PCM audio over WebSocket binary frames; `process_audio(client_id, data)` runs detection and returns matches. Per-client pause/resume state for muting during TTS playback.

**`app/heartbeat.py`** — Background heartbeat system. `start_heartbeat(config, chat_handler)` spawns the async loop. Tracks user idle time via `record_user_interaction()`. Pauses until user responds before sending another heartbeat.

**`app/chat.py`** — Chat handler. Manages conversation history, LLM calls via OpenAI SDK, and tool execution loop (up to `MAX_TOOL_ROUNDS=10` iterations). Built-in tools: `play_animation`, `memory_create/read/edit/patch/delete/list`, `state_set/get/list/check_time`, `web_search` (Brave Search, when enabled). Also routes to MCP tools. The system prompt is built from `state/soul/` markdown files (excluding `heartbeat.md`), loaded once at init. Has a separate `heartbeat()` method for background prompts. An `asyncio.Lock` protects `_messages` for concurrency safety. `memory_patch` does string replacement (rejects if old_string matches 0 or >1 times).

**`app/auth.py`** — Token-based API authentication. `init_auth(config)` loads settings. `require_auth` is a FastAPI dependency added to all protected routes — extracts `Authorization: Bearer <token>` and validates against the configured API key using `hmac.compare_digest()`. `require_ws_auth(websocket)` checks token from `?token=` query param. Routes: `POST /api/auth/login`, `GET /api/auth/check`, `GET /api/auth/status`. No-ops when auth is disabled.

**`app/mcp_manager.py`** — MCP client manager. Connects to configured MCP servers via stdio on startup, discovers their tools, converts tool schemas to OpenAI function-calling format, and routes tool calls to the correct server session.

**`static/`** — Frontend ES modules served via FastAPI's StaticFiles mount:
- `auth.js` — Auth module. `getToken()`/`setToken()`/`clearToken()` manage localStorage. `authFetch()` wraps `fetch()` with Bearer token header (shows login on 401). `checkAuth()` gates app init behind auth validation.
- `app.js` — Entry point. Auth gate via `checkAuth()`, then loads VRM, preloads animations, starts render loop, initializes chat and wake word.
- `animations.js` — Mixamo FBX-to-VRM retargeting. Crossfade blending between animations (0.3s transitions).
- `websocket.js` — Auto-reconnecting WebSocket for animation playback, heartbeat, TTS audio playback, and wake word detection events. Exports `getWebSocket()` for the wakeword module to send binary audio. Pauses/resumes wake word during audio. Triggers auto-listen window after TTS playback. Appends `?token=...` for auth. Background tabs skip audio playback (`document.hidden`).
- `chat.js` — Chat UI, push-to-talk mic recording, sends audio to `/api/transcribe`. `sendMessage()` is exported for use by other modules (wake word). All fetch calls use `authFetch()`. Assistant messages are rendered as markdown via `marked.js` (CDN).
- `wakeword.js` — Streams mic audio to server for wake word detection. AudioWorklet resamples to 16kHz Int16 PCM and sends binary frames over WebSocket. On server detection event: records speech via MediaRecorder, transcribes via `/api/transcribe`, sends through chat. Sends pause/resume control messages during TTS playback. Auto-listen window (5s) after TTS ends if last input was voice. Voice status indicator: listening/recording/transcribing/playing states.
- `settings.js` — Settings panel with tool call toggle, hide UI button, chat history management.

**`assets/wakeword/models/`** — ONNX keyword model files used by server-side openwakeword.

## Key Data Flow

```
Browser chat input → POST /api/chat → ChatHandler.send_message()
  → LLM (OpenAI-compatible API) with tools
  → tool calls (animation/memory/state/MCP) executed in loop
  → final text response returned to browser
  → TTS audio broadcast via WebSocket to all clients
  → animations triggered via WebSocket broadcast
```

### Voice Input Flow

```
Browser AudioWorklet → 16kHz Int16 PCM → WebSocket binary frames
  → Server openwakeword detects keyword → WebSocket JSON notification
  → Browser MediaRecorder starts recording speech
  → silence timeout → stop recording → POST /api/transcribe
  → faster-whisper transcribes in-process → text returned
  → auto-sent through normal chat flow
```

Push-to-talk (Mic button) follows the same `/api/transcribe` path but is manually triggered.

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
  "stt": {                          // Optional: faster-whisper speech-to-text
    "enabled": false,
    "model": "large-v3",            // Whisper model size
    "device": "cuda",               // "cuda", "cpu", or "auto"
    "compute_type": "float16",      // "float16", "int8", etc.
    "language": "en"                // Force language (omit for auto-detect)
  },
  "wakeword": {                     // Optional: server-side wake word detection
    "enabled": false,
    "keyword": "hey_jarvis",        // Must match a model in assets/wakeword/models/
    "model_file": "custom.onnx",    // Optional: override model filename
    "auto_start": false             // Auto-enable wake word, hide wake button
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
  "brave": {                         // Optional: Brave Search web tool
    "enabled": false,
    "api_key": "BSA..."
  },
  "auth": {                           // Optional: API authentication
    "enabled": false,
    "api_key": "your-secret-key"     // Shared secret for all clients
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

## Docker

```bash
# Build and run with docker-compose (GPU)
docker compose up --build

# Run CPU-only (no STT)
docker compose up --build
# (remove the deploy.resources section from docker-compose.yml)
```

`Dockerfile` uses `nvidia/cuda:12.4.1-runtime-ubuntu22.04` with Python 3.12 and Node.js 22. Runtime data (`config.json`, `assets/`, `state/`) is bind-mounted, not baked into the image.

## Adding Animations

Drop Mixamo FBX files (exported as **FBX Binary**, **Without Skin**) into `assets/anims/` and restart. The filename stem becomes the animation name. VRM model files go in `assets/models/`.

## Adding Wake Word Models

Drop `.onnx` keyword model files into `assets/wakeword/models/` and set `wakeword.keyword` in `config.json` — the model file defaults to `{keyword}.onnx`. Optionally set `wakeword.model_file` to override the filename.

## Animation Retargeting

Mixamo FBX animations are retargeted to VRM in the browser. `loadMixamoAnimation()` in `static/js/animations.js` extracts world rest rotations from FBX bones and transforms keyframes: `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Git-ignored Assets

`assets/`, `state/`, `venv/`, `__pycache__/`, `config.json`

## Dependencies

- **Python:** fastapi, uvicorn[standard], openai, mcp, httpx, faster-whisper, nvidia-cublas-cu12, brave-search-python-client, psutil, openwakeword
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2, marked.js
