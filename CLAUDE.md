# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI chatbot with a 3D VRM avatar. FastAPI backend controls a Three.js browser frontend via WebSocket. The LLM can trigger character animations, manage persistent memories, and use external tools via MCP servers. Features include TTS (GPT-SoVITS), STT (faster-whisper), browser-side wake word detection (openWakeWord via ONNX), and a background heartbeat system for proactive AI messages.

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

**`app/server.py`** — FastAPI server. Manages app lifecycle (MCP startup/shutdown, STT model loading, heartbeat task), WebSocket connections to browsers, REST API endpoints. Routes: `/` (frontend), `/api/chat` (POST), `/api/animations` (GET), `/api/play/{name}` (POST), `/api/chat/clear` (POST), `/api/stt/status` (GET), `/api/transcribe` (POST), `/ws` (WebSocket). Blocking operations (STT model load, transcription) run in thread executors to avoid blocking the async event loop. NVIDIA CUDA libraries from pip packages are pre-loaded via `ctypes` at startup.

**`app/chat.py`** — Chat handler. Manages conversation history, LLM calls via OpenAI SDK, and tool execution loop (up to `MAX_TOOL_ROUNDS=10` iterations). Built-in tools: `play_animation`, `memory_create/read/edit/delete/list`, `state_set/get/list/check_time`. Also routes to MCP tools. The system prompt is built from `state/soul/` markdown files (excluding `heartbeat.md`), loaded once at init. Has a separate `heartbeat()` method for background prompts. An `asyncio.Lock` protects `_messages` for concurrency safety.

**`app/mcp_manager.py`** — MCP client manager. Connects to configured MCP servers via stdio on startup, discovers their tools, converts tool schemas to OpenAI function-calling format, and routes tool calls to the correct server session.

**`static/`** — Frontend ES modules served via FastAPI's StaticFiles mount:
- `app.js` — Entry point. Loads VRM, preloads animations, starts render loop, initializes chat and wake word.
- `animations.js` — Mixamo FBX-to-VRM retargeting.
- `websocket.js` — Auto-reconnecting WebSocket for animation playback, heartbeat, TTS audio playback. Pauses/resumes wake word during audio. Background tabs skip audio playback (`document.hidden`).
- `chat.js` — Chat UI, push-to-talk mic recording, sends audio to `/api/transcribe`. `sendMessage()` is exported for use by other modules (wake word).
- `wakeword.js` — Browser-side wake word detection using `WakeWordEngine` (ONNX/WASM). On detection: records speech via MediaRecorder, auto-stops on silence (VAD speech-end), transcribes via `/api/transcribe`, sends through chat. Pauses during TTS playback to avoid self-triggering. Keyword is configurable from server config.

**`static/wakeword/`** — Vendored openWakeWord assets:
- `WakeWordEngine.js` — Modified from [openwakeword_wasm](https://github.com/dnavarrom/openwakeword_wasm). Uses `globalThis.ort` (loaded via CDN script tag, not ES import). AudioWorklet downsamples from native sample rate to 16kHz for cross-browser compatibility.
- `models/` — ONNX model files (melspectrogram, embedding, VAD, keyword models).

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
Wake word detected in browser (ONNX/WASM) → MediaRecorder starts
  → VAD speech-end → stop recording → POST /api/transcribe
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
  "wakeword": {                     // Optional: browser-side wake word
    "keyword": "hey_jarvis"         // Must match a model in static/wakeword/models/
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

## Adding Wake Word Models

Drop `.onnx` keyword model files into `static/wakeword/models/` and add the keyword-to-filename mapping in `WakeWordEngine.js`'s `MODEL_FILE_MAP`. Set `wakeword.keyword` in `config.json` to match.

## Animation Retargeting

Mixamo FBX animations are retargeted to VRM in the browser. `loadMixamoAnimation()` in `static/js/animations.js` extracts world rest rotations from FBX bones and transforms keyframes: `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Git-ignored Assets

`assets/`, `state/`, `venv/`, `__pycache__/`, `config.json`

## Dependencies

- **Python:** fastapi, uvicorn[standard], openai, mcp, httpx, faster-whisper, nvidia-cublas-cu12
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2, onnxruntime-web 1.21.0
