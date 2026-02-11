# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI chatbot with a 3D VRM avatar. FastAPI backend controls a Three.js browser frontend via WebSocket. The LLM can trigger character animations, manage persistent memories, and use external tools via MCP servers.

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

Three Python modules + one frontend file:

**`server.py`** — FastAPI server. Manages app lifecycle (MCP startup/shutdown), WebSocket connections to browsers, REST API endpoints. Routes: `/` (frontend), `/api/chat` (POST), `/api/animations` (GET), `/api/play/{name}` (POST), `/api/chat/clear` (POST), `/ws` (WebSocket).

**`chat.py`** — Chat handler. Manages conversation history, LLM calls via OpenAI SDK, and tool execution loop (up to `MAX_TOOL_ROUNDS=10` iterations). Built-in tools: `play_animation`, `memory_create`, `memory_read`, `memory_edit`, `memory_delete`, `memory_list`. Also routes to MCP tools. The system prompt is built from `soul/` markdown files, loaded once at init.

**`mcp_manager.py`** — MCP client manager. Connects to configured MCP servers via stdio on startup, discovers their tools, converts tool schemas to OpenAI function-calling format, and routes tool calls to the correct server session. Custom env vars are merged with the current environment (so `PATH` is preserved for commands like `npx`).

**`static/index.html`** — Self-contained Three.js app. Loads VRM model, preloads Mixamo FBX animations, connects WebSocket for real-time animation commands, and has a chat UI that POSTs to `/api/chat`.

## Key Data Flow

```
Browser chat input → POST /api/chat → ChatHandler.send_message()
  → LLM (OpenAI-compatible API) with tools
  → tool calls (animation/memory/MCP) executed in loop
  → final text response returned to browser
  → animations triggered via WebSocket broadcast to all clients
```

## Configuration

**`config.json`** — LLM endpoint and MCP servers. Supports both `mcp_servers` and `mcpServers` (LM Studio format) keys.

**`soul/*.md`** — Personality/identity files loaded alphabetically into the system prompt at startup. Restart server to pick up changes.

**`memories/*.md`** — Persistent memory files created/managed by the LLM via tool calls. Filenames are sanitized to prevent path traversal.

## Adding Animations

Drop Mixamo FBX files (exported as **FBX Binary**, **Without Skin**) into `anims/` and restart. The filename stem becomes the animation name.

## Animation Retargeting

Mixamo FBX animations are retargeted to VRM in the browser. `loadMixamoAnimation()` extracts world rest rotations from FBX bones and transforms keyframes: `parentRestWorld * animQuat * restWorldInverse`. The `mixamoToVRMBone()` map translates Mixamo rig names to VRM humanoid bone names.

## Git-ignored Assets

`*.vrm`, `anims/`, `memories/`, `soul/`, `venv/`, `__pycache__/`

## Dependencies

- **Python:** fastapi, uvicorn[standard], openai, mcp
- **Browser (CDN):** three.js 0.162.0, @pixiv/three-vrm 3.3.2
