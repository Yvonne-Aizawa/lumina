"""Server-side wake word detection using openwakeword."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .config import WakeWordConfig

log = logging.getLogger(__name__)

_model = None
_keyword: str = "hey_jarvis"
_threshold: float = 0.5
_cooldown_ms: int = 2000
_enabled: bool = False

# Per-client state: {client_id: {"paused": bool, "last_detection": float}}
_clients: dict[int, dict] = {}


async def init_wakeword(config: WakeWordConfig):
    """Load the openwakeword model at startup."""
    global _model, _keyword, _enabled

    if not config.enabled:
        return

    _keyword = config.keyword

    try:
        from openwakeword.model import Model as OWWModel

        from .config import PROJECT_DIR

        models_dir = PROJECT_DIR / "static" / "wakeword" / "models"

        # Resolve model file path
        if config.model_file:
            model_path = str(models_dir / config.model_file)
        else:
            model_path = str(models_dir / f"{config.keyword}.onnx")

        log.info(f"Loading wake word model: {model_path}")
        _model = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: OWWModel(wakeword_model_paths=[model_path]),
        )
        log.info(
            f"Wake word model loaded (keyword={_keyword}, "
            f"models={list(_model.models.keys())})"
        )
        _enabled = True
    except Exception:
        log.exception("Failed to load wake word model")


def is_enabled() -> bool:
    return _enabled


def get_keyword() -> str:
    return _keyword


def register_client(client_id: int):
    _clients[client_id] = {"paused": False, "last_detection": 0.0}


def remove_client(client_id: int):
    _clients.pop(client_id, None)


def pause(client_id: int):
    if client_id in _clients:
        _clients[client_id]["paused"] = True


def resume(client_id: int):
    if client_id in _clients:
        _clients[client_id]["paused"] = False
        if _model:
            _model.reset()


def process_audio(client_id: int, data: bytes) -> dict | None:
    """Process a binary audio chunk. Returns detection dict or None."""
    if not _model or not _enabled:
        return None

    state = _clients.get(client_id)
    if not state or state["paused"]:
        return None

    audio = np.frombuffer(data, dtype=np.int16)
    prediction = _model.predict(audio)

    for model_name, score in prediction.items():
        if score < _threshold:
            continue
        now = time.monotonic()
        if (now - state["last_detection"]) * 1000 < _cooldown_ms:
            continue
        state["last_detection"] = now
        _model.reset()
        return {"keyword": _keyword, "score": float(score)}

    return None
