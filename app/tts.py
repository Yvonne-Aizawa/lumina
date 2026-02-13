"""TTS (text-to-speech) synthesis client."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

import httpx

from .broadcast import broadcast

if TYPE_CHECKING:
    from .config import TTSConfig

log = logging.getLogger(__name__)

tts_config: TTSConfig | None = None


def init_tts(config: TTSConfig):
    """Initialise TTS from the app config. Call once at startup."""
    global tts_config
    if config.enabled:
        tts_config = config
        log.info(f"TTS enabled (server: {config.base_url})")


async def synthesize_and_broadcast(text: str):
    """Call GPT-SoVITS to synthesize speech and broadcast audio to all clients."""
    if not tts_config or not tts_config.enabled:
        return
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{tts_config.base_url}/tts",
                json={
                    "text": text,
                    "text_lang": tts_config.text_lang,
                    "ref_audio_path": tts_config.ref_audio_path,
                    "prompt_text": tts_config.prompt_text,
                    "prompt_lang": tts_config.prompt_lang,
                },
            )
            if resp.status_code == 200:
                audio_b64 = base64.b64encode(resp.content).decode("ascii")
                await broadcast({"action": "audio", "data": audio_b64})
            else:
                log.warning(f"TTS failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        log.exception("TTS synthesis error")
