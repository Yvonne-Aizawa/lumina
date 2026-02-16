"""State tool handlers."""

import json
from datetime import datetime, timezone

from ._common import state_path


def _load_state() -> dict:
    if state_path().exists():
        try:
            return json.loads(state_path().read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict):
    state_path().write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def handle_state_set(arguments: dict) -> str:
    key = str(arguments.get("key", "")).strip()
    if not key:
        return "Error: key is required."
    value = arguments.get("value")
    if value == "now":
        value = datetime.now(timezone.utc).isoformat()
    state = _load_state()
    state[key] = value
    _save_state(state)
    return f"State '{key}' set to {json.dumps(value)}."


def handle_state_get(arguments: dict) -> str:
    key = str(arguments.get("key", "")).strip()
    if not key:
        return "Error: key is required."
    state = _load_state()
    if key not in state:
        return f"Key '{key}' not found."
    return f"{key}: {json.dumps(state[key])}"


def handle_state_list() -> str:
    state = _load_state()
    if not state:
        return "State is empty."
    lines = [f"- {k}: {json.dumps(v)}" for k, v in state.items()]
    return "State:\n" + "\n".join(lines)


def handle_state_check_time(arguments: dict) -> str:
    key = arguments.get("key", "").strip()
    if not key:
        return "Error: key is required."
    state = _load_state()
    if key not in state:
        return f"Key '{key}' not found."
    value = state[key]
    try:
        ts = datetime.fromisoformat(value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - ts
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(abs(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        human = " ".join(parts)
        return f"'{key}' was {human} ago ({total_seconds} seconds). Timestamp: {value}"
    except (ValueError, TypeError):
        return f"Error: '{key}' value '{value}' is not a valid timestamp."
