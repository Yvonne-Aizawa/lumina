# API Endpoints Documentation

This document describes all available API endpoints for the AI Waifu project.

## Authentication

The API supports optional token-based authentication. When auth is enabled in `config.json`, all protected endpoints require either:
- HTTP Header: `Authorization: Bearer <token>`
- WebSocket Query Param: `?token=<token>`

### Authentication Endpoints

#### POST `/api/auth/login`
Login with API key to receive the bearer token.

**Request Body:**
```json
{
  "api_key": "your-secret-key"
}
```

**Response:**
```json
{
  "token": "your-secret-key",
  "auth_enabled": true
}
```

#### GET `/api/auth/check`
Check if current request is authenticated.

**Headers:** `Authorization: Bearer <token>` (when auth enabled)

**Response:**
```json
{
  "authenticated": true,
  "auth_enabled": true
}
```

#### GET `/api/auth/status`
Check if authentication is enabled on the server (public endpoint).

**Response:**
```json
{
  "auth_enabled": true
}
```

## Chat API

### POST `/api/chat`
Send a message to the AI character.

**Authentication:** Required

**Request Body:**
```json
{
  "message": "Hello, how are you?",
  "stream": false
}
```

**Parameters:**
- `message` (required): The message to send
- `stream` (optional): `true` for streaming, `false` for non-streaming, or omit to use system default

**Response (non-streaming):**
```json
{
  "response": "I'm doing well, thank you for asking!"
}
```

**Response (streaming):**
When `stream: true` is set (or system default is streaming), the response is a server-sent events (SSE) stream with these events:
```
data: {"type": "content", "content": "I'm"}
data: {"type": "content", "content": " doing"}
data: {"type": "content", "content": " well"}
data: {"type": "done", "content": "I'm doing well, thank you for asking!"}
```

Event types:
- `content`: Partial text content
- `done`: Final complete response
- `error`: Error message

**System Default Behavior:**
If the `stream` parameter is omitted, the system uses the default_mode from the streaming configuration in `config.json`. This allows administrators to set system-wide preferences while still allowing clients to override when needed.

### POST `/api/chat/clear`
Clear the current chat history.

**Authentication:** Required

**Response:**
```json
{
  "status": "ok"
}
```

### GET `/api/chats`
List all chat sessions and current session.

**Authentication:** Required

**Response:**
```json
{
  "sessions": ["session_1", "session_2"],
  "current": "session_1"
}
```

### POST `/api/chats/new`
Create a new chat session.

**Authentication:** Required

**Response:**
```json
{
  "status": "ok",
  "id": "new_session_id"
}
```

### POST `/api/chats/load`
Load a specific chat session.

**Authentication:** Required

**Request Body:**
```json
{
  "id": "session_id_to_load"
}
```

**Response:**
```json
{
  "status": "ok",
  "id": "session_id_to_load",
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"}
  ]
}
```

## Animation API

### GET `/api/animations`
List all available animations.

**Authentication:** Required

**Response:**
```json
{
  "animations": ["idle", "wave", "dance", "walk"]
}
```

### POST `/api/play/{animation_name}`
Play a specific animation.

**Authentication:** Required

**Parameters:**
- `animation_name` (path): Name of the animation to play

**Response:**
```json
{
  "status": "ok",
  "animation": "wave"
}
```

**Error Response:**
```json
{
  "error": "Unknown animation: invalid_anim",
  "available": ["idle", "wave", "dance", "walk"]
}
```

## Speech-to-Text API

### GET `/api/stt/status`
Check STT and wake word status.

**Authentication:** Required

**Response:**
```json
{
  "enabled": true,
  "wakeword": "hey_jarvis",
  "wakeword_enabled": true,
  "wakeword_auto_start": false
}
```

### POST `/api/transcribe`
Transcribe audio file to text.

**Authentication:** Required

**Request:** Multipart form with audio file

**Response:**
```json
{
  "text": "Hello, how are you?"
}
```

**Error Response (STT disabled):**
```json
{
  "error": "STT not enabled"
}
```

### GET `/api/streaming/status`
Get current streaming configuration.

**Authentication:** Required

**Response:**
```json
{
  "enabled": true,
  "default_mode": "streaming",
  "auto_fallback": true
}
```

## WebSocket API

### WebSocket `/ws`
Real-time communication for animations, TTS audio, and wake word detection.

**Authentication:** Token via query param `?token=<token>`

**Message Types:**

**Server to Client:**
```json
{
  "action": "chat",
  "content": "AI response message"
}
```

```json
{
  "action": "play_animation",
  "animation": "wave"
}
```

```json
{
  "action": "audio",
  "audio": "base64_encoded_audio_data"
}
```

```json
{
  "action": "wakeword_detected",
  "keyword": "hey_jarvis",
  "confidence": 0.95
}
```

**Client to Server:**
- Binary audio data for wake word detection (16kHz Int16 PCM)
```json
{
  "action": "wakeword_pause"
}
```
```json
{
  "action": "wakeword_resume"
}
```

## Static Assets

### GET `/`
Serve the main frontend page.

### GET `/avatar.vrm`
Serve the VRM avatar model file.

### `/anims/{animation_file}`
Serve animation files (Mixamo FBX).

### `/static/{path}`
Serve frontend static assets.

## Error Responses

Most endpoints return errors in this format:

**Authentication Error (401):**
```json
{
  "detail": "Unauthorized"
}
```

**Other Errors:**
```json
{
  "error": "Error description"
}
```

## Configuration

The API behavior is controlled by `config.json`:

```json
{
  "llm": {
    "base_url": "http://localhost:1234/v1",
    "api_key": "...",
    "model": "model-name"
  },
  "stt": {
    "enabled": false,
    "model": "large-v3",
    "device": "cuda",
    "compute_type": "float16",
    "language": "en"
  },
  "wakeword": {
    "enabled": false,
    "keyword": "hey_jarvis",
    "model_file": "custom.onnx",
    "auto_start": false
  },
  "tts": {
    "enabled": false,
    "base_url": "http://localhost:9880",
    "ref_audio_path": "/path/to/reference.wav",
    "prompt_text": "...",
    "prompt_lang": "en",
    "text_lang": "en"
  },
  "heartbeat": {
    "enabled": false,
    "interval": 600,
    "idle_threshold": 1200
  },
  "brave": {
    "enabled": false,
    "api_key": "BSA..."
  },
  "auth": {
    "enabled": false,
    "api_key": "your-secret-key"
  },
  "streaming": {
    "enabled": true,
    "default_mode": "streaming",
    "auto_fallback": true
  },
  "mcpServers": {
    "server-name": {
      "command": "...",
      "args": [],
      "env": {}
    }
  }
}
```

### Streaming Configuration

The `streaming` section controls how chat responses are delivered:

- `enabled`: (boolean) Whether streaming is available at all (default: true)
- `default_mode`: (string) "streaming" or "non-streaming" - the default behavior when no stream parameter is specified (default: "streaming")
- `auto_fallback`: (boolean) Whether to automatically fall back to non-streaming if streaming fails (default: true)