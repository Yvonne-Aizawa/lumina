# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Lumina** — AI chatbot with a 3D VRM avatar. FastAPI backend controls a Three.js browser frontend via WebSocket. The LLM can trigger character animations, manage persistent memories, store embeddings in a vector database, create its own sandboxed MCP tool servers, and use external tools via MCP servers. Features include TTS (GPT-SoVITS or Qwen3-TTS), STT (faster-whisper), server-side wake word detection (openwakeword), emotion detection with VRM facial expressions, and a background heartbeat system for proactive AI messages.

## Running the Project

Requires Python 3.12+ and optionally Node.js 22+ (for MCP servers that use `npx`). NVIDIA GPU + CUDA optional for STT acceleration.

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

**`app/server.py`** — FastAPI app and lifespan orchestrator. The lifespan function calls init functions from the subsystem modules below. All API routes use `Depends(require_auth)`; WebSocket checks token via query param; static files, `/`, `/memory`, and `/api/auth/*` are unprotected.

**`app/routes/`** — Route handlers split into modules: `pages.py` (HTML pages), `chat.py` (`/api/chat`, `/api/chats`), `animations.py` (`/api/animations`, `/api/backgrounds`, `/api/play`), `stt.py` (`/api/stt/status`, `/api/transcribe`), `vector.py` (`/api/vector` CRUD), `websocket.py` (`/ws`). Auth routes are mounted from `app/auth.py`.

**`app/config.py`** — Path constants (`PROJECT_DIR`, `ASSETS_DIR`, `ANIMS_DIR`, `MODELS_DIR`, `STATE_DIR`, `VRM_MODEL`, `CONFIG_PATH`) and `load_config()`. Paths are overridable via `state_dir`, `assets_dir`, and `vrm_model` in config.json. Configuration uses dataclasses: `BuiltinToolsConfig` has nested `WebSearchConfig` and `VectorSearchConfig`.

**`app/broadcast.py`** — WebSocket client list and `broadcast()` for sending JSON to all connected browsers. Also contains animation/background helpers: `list_animations()`, `list_backgrounds()`, `play_animation()`, `set_background()`, `notify_tool_call()`.

**`app/tts.py`** — TTS client with configurable provider. `init_tts(config)` loads settings (and the Qwen3-TTS model if selected). `synthesize_and_broadcast(text)` synthesizes speech and broadcasts base64 WAV audio via WebSocket. Supports `"gpt-sovits"` (HTTP API) and `"qwen3-tts"` (local model, runs inference in thread executor). TTS is fired as a background task from the chat route so text responses return immediately.

**`app/emotion.py`** — Emotion detection using HuggingFace transformers (`j-hartmann/emotion-english-distilroberta-base`). `init_emotion(config)` loads model at startup. `detect_emotion(text)` maps detected emotions to VRM facial expressions. Runs inference in thread executor.

**`app/stt.py`** — STT model. `init_stt(config)` loads faster-whisper in a thread executor (with NVIDIA CUDA libraries pre-loaded via `ctypes`). `transcribe(audio_bytes)` runs transcription in a thread executor. `is_enabled()` getter returns live state (do not import the `stt_enabled` variable directly — it's set after import time).

**`app/wakeword.py`** — Server-side wake word detection using openwakeword. `init_wakeword(config)` loads the ONNX keyword model at startup. Browser streams 16kHz Int16 PCM audio over WebSocket binary frames; `process_audio(client_id, data)` runs detection and returns matches. Per-client pause/resume state for muting during TTS playback.

**`app/heartbeat.py`** — Background heartbeat system. `start_heartbeat(config, chat_handler)` spawns the async loop. Tracks user idle time via `record_user_interaction()`. Pauses until user responds before sending another heartbeat.

**`app/chat.py`** — Chat handler. Manages conversation history, LLM calls via OpenAI SDK, and tool execution loop (up to `MAX_TOOL_ROUNDS=10` iterations). The system prompt is built from `state/soul/` markdown files (excluding `heartbeat.md`), loaded once at init. Has a separate `heartbeat()` method for background prompts. An `asyncio.Lock` protects `_messages` for concurrency safety.

**`app/tools/`** — Tool definitions and handlers, split into modules:
- `__init__.py` — Re-exports: `get_builtin_tools`, `handle_tool_call`, `init_vector_search`, `start_servers_from_manifest`
- `_definitions.py` — `get_builtin_tools()` returns all tool schemas in OpenAI function-calling format, gated by `BuiltinToolsConfig`
- `_dispatch.py` — `handle_tool_call()` central dispatcher. Checks built-in tools first, then falls through to `mcp_manager.call_tool()`
- `_common.py` — Shared helpers: `memories_dir()`, `state_path()`, `safe_filename()`, `git_commit()`
- `_memory.py` — Memory CRUD: `handle_memory_create/read/edit/delete/patch/list`. `memory_patch` does string replacement (rejects if old_string matches 0 or >1 times). Changes are automatically git-committed
- `_state.py` — Persistent key-value store: `handle_state_set/get/list/check_time`
- `_web_search.py` — Brave Search: `handle_web_search`
- `_bash.py` — Shell commands: `handle_run_command`
- `_vector.py` — ChromaDB + Ollama embeddings: `init_vector_search`, `get_collection()`, `handle_vector_save/search/delete/list`
- `_mcp_servers.py` — AI-created MCP server management: `handle_mcp_server_create/edit/delete/list/start/stop/logs`, `start_servers_from_manifest()`

**`app/sandbox.py`** — Sandbox utilities for AI-created MCP servers. AST-based code validation (`validate_code()`) blocks dangerous imports/calls/dunder attributes. `build_wrapper_script()` generates a Python script that installs a runtime import hook before executing the server. `build_sandbox_env()` builds a minimal environment dict.

**`app/mcp_manager.py`** — MCP client manager. Connects to configured MCP servers via stdio on startup, discovers their tools, converts tool schemas to OpenAI function-calling format, and routes tool calls to the correct server session. Also manages AI-created servers with `start_ai_server()`/`stop_ai_server()` — each runs in a sandboxed subprocess with stderr captured to a log file.

**`app/auth.py`** — Token-based API authentication. `require_auth` is a FastAPI dependency. `require_ws_auth(websocket)` checks token from `?token=` query param. No-ops when auth is disabled.

**`static/`** — Frontend ES modules served via FastAPI's StaticFiles mount:
- `auth.js` — Auth module. `authFetch()` wraps `fetch()` with Bearer token. `checkAuth()` gates app init. `initAuth()` wires up login form.
- `app.js` — Entry point. Auth gate, then loads VRM, starts render loop (with random blinking), initializes chat and wake word.
- `scene.js` — Three.js scene, camera, lighting, and renderer setup.
- `animations.js` — Mixamo FBX-to-VRM retargeting with crossfade blending (0.3s transitions).
- `websocket.js` — Auto-reconnecting WebSocket for animations, heartbeat, TTS audio, and wake word events. Pauses/resumes wake word during audio. Background tabs skip audio playback.
- `chat.js` — Chat UI, push-to-talk mic recording. `sendMessage()` exported for wake word module. Markdown rendering via `marked.js` (CDN).
- `wakeword.js` — AudioWorklet resamples to 16kHz Int16 PCM, streams over WebSocket. Auto-listen window after TTS. Voice status indicator.
- `settings.js` — Settings panel with tool call toggle, hide UI, chat history management.
- `memory.js` — Vector DB memory manager UI. Uses `authFetch`, client-side search filtering, edit/delete with Ctrl+S save.
- `memory.html` — Standalone page for `/memory` route.

## Key Data Flow

```
Browser chat input → POST /api/chat → ChatHandler.send_message()
  → LLM (OpenAI-compatible API) with tools
  → tool calls (animation/memory/state/vector/MCP) executed in loop
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

**`config.json`** (git-ignored) — Main configuration file. Copy from `config.example.json`:

```jsonc
{
  "llm": {
    "base_url": "http://localhost:1234/v1",  // OpenAI-compatible endpoint
    "api_key": "...",
    "model": "model-name"
  },
  "stt": {                          // Optional: faster-whisper speech-to-text
    "enabled": false,
    "model": "large-v3",
    "device": "auto",               // "cuda", "cpu", or "auto"
    "compute_type": "float16",
    "language": "en"
  },
  "wakeword": {                     // Optional: server-side wake word detection
    "enabled": false,
    "keyword": "hey_jarvis",
    "auto_start": false
  },
  "tts": {                          // Optional: text-to-speech
    "enabled": false,
    "provider": "gpt-sovits",       // "gpt-sovits" or "qwen3-tts"
    "base_url": "http://localhost:9880",  // GPT-SoVITS only
    "ref_audio_path": "/path/to/reference.wav",
    "prompt_text": "...",
    "prompt_lang": "en",
    "text_lang": "en",
    "qwen3_model": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",  // Qwen3-TTS only
    "qwen3_device": "cuda:0",
    "qwen3_language": "English",
    "qwen3_instruct": ""
  },
  "heartbeat": {                     // Optional: proactive messages
    "enabled": false,
    "interval": 600,
    "idle_threshold": 1200
  },
  "auth": {                           // Optional: API authentication
    "enabled": false,
    "api_key": "your-secret-key"
  },
  "builtin_tools": {                 // Optional: toggle built-in tool groups
    "animation": true,
    "memory": true,
    "memory_readonly": false,        // true = only memory_read/list, no write tools
    "state": true,
    "web_search": {
      "enabled": false,
      "brave": {
        "enabled": false,
        "api_key": "BSA..."
      }
    },
    "vector_search": {               // ChromaDB + Ollama embeddings
      "enabled": false,
      "ollama_url": "http://localhost:11434",
      "model": "nomic-embed-text",
      "collection": "memories"
    },
    "bash": true,                    // run_command (also requires top-level bash.enabled)
    "mcp_servers": false             // AI-created sandboxed MCP servers
  },
  "bash": { "enabled": false },
  "state_dir": "/custom/path/to/state",   // Optional: override state directory
  "assets_dir": "/custom/path/to/assets", // Optional: override assets directory
  "vrm_model": "avatar.vrm",              // Optional: override VRM model filename
  "mcpServers": {                    // Optional: external MCP tool servers
    "server-name": {
      "command": "...",
      "args": [],
      "env": {}
    }
  }
}
```

**`state/soul/*.md`** — Personality/identity files loaded alphabetically into the system prompt at startup. `heartbeat.md` is excluded from the system prompt and used only by the heartbeat system. Restart server to pick up changes.

**`state/memories/*.md`** — Persistent memory files created/managed by the LLM via tool calls. Filenames are sanitized to prevent path traversal. Changes are automatically git-committed.

**`state/state.json`** — Persistent key-value state store managed by the LLM via `state_*` tools.

**`state/vectordb/`** — ChromaDB persistent storage (when vector_search is enabled). Uses Ollama for embeddings.

**`state/mcp_servers/`** — AI-created MCP servers (when mcp_servers is enabled). Each server gets a subdirectory with `server.py`, `_wrapper.py`, `sandbox/`, and `stderr.log`. `manifest.json` tracks server metadata and auto-start preferences.

## AI-Created MCP Servers

When `builtin_tools.mcp_servers` is enabled, the AI can create Python MCP tool servers at runtime using `mcp_server_create`. Servers use `mcp.server.fastmcp.FastMCP` (from the `mcp` package) and run in sandboxed subprocesses.

**Sandboxing (3 layers):**
1. AST validation (`app/sandbox.py:validate_code`) — blocks dangerous imports (`os`, `subprocess`, `shutil`, etc.), calls (`eval`, `exec`, `__import__`), and dunder attribute access
2. Runtime import hook — `sys.meta_path` finder injected via wrapper script blocks non-allowed modules
3. Process isolation — Python `-I` flag, minimal environment, `cwd` restricted to server directory

Allowed imports: `mcp`, `json`, `datetime`, `math`, `re`, `collections`, `typing`, `dataclasses`, `enum`, `time`, `string`, `random`, `itertools`, `functools`, `hashlib`, `base64`, `textwrap`, `uuid`, `logging`, `io`, and more safe stdlib. Network modules require `allow_network=true`. Servers access per-server file storage via `os.environ["MCP_SANDBOX_DIR"]`.

## Docker

```bash
docker compose up --build
```

`Dockerfile` uses `nvidia/cuda:12.4.1-runtime-ubuntu22.04` with Python 3.12 and Node.js 22. Runtime data (`config.json`, `assets/`, `state/`) is bind-mounted, not baked into the image.

## Adding Animations

Drop Mixamo FBX files (exported as **FBX Binary**, **Without Skin**) into `assets/anims/` and restart. The filename stem becomes the animation name. VRM model files go in `assets/models/`.

## Animation Retargeting

Mixamo FBX animations are retargeted to VRM in the browser. `loadMixamoAnimation()` in `static/js/animations.js` extracts world rest rotations from FBX bones and transforms keyframes: `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Git-ignored Assets

`assets/`, `state/`, `venv/`, `__pycache__/`, `config.json`

## Dependencies

- **Python:** fastapi, uvicorn[standard], openai, mcp, httpx, chromadb, ollama, faster-whisper, nvidia-cublas-cu12, brave-search-python-client, psutil, openwakeword, transformers, torch, qwen-tts, flash-attn, soundfile
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2, marked.js
