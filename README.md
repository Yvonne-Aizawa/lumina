# Lumina

AI chatbot with a 3D VRM avatar. A FastAPI backend controls a Three.js browser frontend via WebSocket. The LLM can trigger character animations, manage persistent memories, and use external tools via MCP servers.

## Features

- 3D VRM avatar with Mixamo animation retargeting and random blinking
- Any OpenAI-compatible LLM backend
- Text-to-speech via [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
- Speech-to-text via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- Server-side wake word detection via [openWakeWord](https://github.com/dscripka/openWakeWord)
- Persistent memory and state system (git-tracked)
- Typing indicator while the LLM is responding
- Background heartbeat for proactive AI messages
- Web search via [Brave Search API](https://brave.com/search/api/)
- Optional sandboxed bash command execution for the LLM
- Extensible tool system via [MCP](https://modelcontextprotocol.io/) servers
- Docker support with NVIDIA GPU passthrough

## Setup

### Requirements

- Python 3.12+
- Node.js 22+ (only if using MCP servers that rely on `npx`)
- NVIDIA GPU + CUDA (optional, for STT acceleration)

### Installation

```bash
git clone https://github.com/Yvonne-Aizawa/lumina.git
cd lumina
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Assets

Place your files in the `assets/` directory (or a custom path via `assets_dir` in config):

- `assets/models/avatar.vrm` — VRM avatar model (filename configurable via `vrm_model` in config)
- `assets/anims/` — Mixamo FBX animations (exported as **FBX Binary**, **Without Skin**)

The filename stem becomes the animation name (e.g. `Waving.fbx` becomes `Waving`). Animations are lazy-loaded on first use.

### Configuration

Copy `config.example.json` to `config.json` and adjust to your setup:

```jsonc
{
  "llm": {
    "base_url": "http://localhost:1234/v1",  // OpenAI-compatible endpoint
    "api_key": "your-api-key",
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
    "prompt_text": "Reference transcript text",
    "prompt_lang": "en",
    "text_lang": "en"
  },
  "heartbeat": {                     // Optional: proactive messages
    "enabled": false,
    "interval": 600,                 // seconds between heartbeat checks
    "idle_threshold": 1200           // seconds of user inactivity before triggering
  },
  "auth": {                           // Optional: API authentication
    "enabled": false,
    "api_key": "your-secret-key"     // Shared secret for all clients
  },
  "bash": {                           // Optional: allow LLM to run shell commands
    "enabled": false
  },
  "builtin_tools": {                 // Optional: toggle built-in tool groups
    "animation": true,               // play_animation, set_background, get_*
    "memory": true,                  // memory_create/read/edit/patch/delete/list
    "state": true,                   // state_set/get/list/check_time
    "web_search": {                  // web_search tool
      "enabled": false,
      "brave": {                     // Brave Search provider
        "enabled": false,
        "api_key": "BSA..."
      }
    },
    "bash": true                     // run_command (also requires bash.enabled)
  },
  "state_dir": "/custom/path/to/state",   // Optional: override state directory
  "assets_dir": "/custom/path/to/assets", // Optional: override assets directory
  "vrm_model": "avatar.vrm",              // Optional: override VRM model filename
  "mcpServers": {                    // Optional: MCP tool servers
    "server-name": {
      "command": "...",
      "args": [],
      "env": {}
    }
  }
}
```

Only the `llm` section is required. All other sections are optional and default to disabled.

### Personality

Create markdown files in `state/soul/` to define the AI's personality and system prompt. Files are loaded alphabetically at startup. Restart the server to pick up changes.

Memory files created by the LLM (in `state/memories/`) are automatically git-committed on each change.

### Running

```bash
python server.py
```

Open http://localhost:8000 in your browser.

## Docker

```bash
docker compose up --build
```

Runtime data (`config.json`, `assets/`, `state/`) is bind-mounted, not baked into the image. The Docker image uses `nvidia/cuda:12.4.1-runtime-ubuntu22.04` with GPU passthrough. For CPU-only usage, remove the `deploy.resources` section from `docker-compose.yml`.

## External Tools

| Tool | Purpose | Required |
|------|---------|----------|
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | Text-to-speech synthesis | Optional |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech-to-text transcription | Optional |
| [openWakeWord](https://github.com/dscripka/openWakeWord) | Server-side wake word detection | Optional |
| [Brave Search API](https://brave.com/search/api/) | Web search tool for the LLM | Optional |
| Any OpenAI-compatible API | LLM backend (e.g. LM Studio, ollama, OpenAI) | **Required** |

GPT-SoVITS must be running separately and accessible at the URL configured in `tts.base_url`. faster-whisper runs in-process and requires NVIDIA CUDA libraries for GPU acceleration. openWakeWord runs server-side; the browser streams mic audio over WebSocket for detection.

## Adding Wake Word Models

1. Drop `.onnx` keyword model files into `assets/wakeword/models/`
2. Set `wakeword.keyword` in `config.json` — the model file defaults to `{keyword}.onnx`
3. Optionally set `wakeword.model_file` to override the filename

## Getting Assets

### VRM Models

You can use [VRoid Studio](https://vroid.com/studio) to make a model. It's free on Steam.

### Animations

Download animations from [Mixamo](https://www.mixamo.com/#/). Export as **FBX Binary**, **Without Skin**.

### Wake Word Models

Community models are available at [openWakeWord Library](https://openwakeword.com/library).

## License

MIT
