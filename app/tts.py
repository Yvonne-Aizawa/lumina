"""TTS (text-to-speech) synthesis client."""

import base64
import logging

import httpx

from .broadcast import broadcast

log = logging.getLogger(__name__)

tts_config: dict | None = None


def init_tts(config: dict):
    """Initialise TTS from the app config. Call once at startup."""
    global tts_config
    tts_cfg = config.get("tts", {})
    if tts_cfg.get("enabled"):
        tts_config = tts_cfg
        log.info(f"TTS enabled (server: {tts_cfg['base_url']})")


async def synthesize_and_broadcast(text: str):
    """Call GPT-SoVITS to synthesize speech and broadcast audio to all clients."""
    if not tts_config or not tts_config.get("enabled"):
        return
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{tts_config['base_url']}/tts",
                json={
                    "text": text,
                    "text_lang": tts_config.get("text_lang", "en"),
                    "ref_audio_path": tts_config.get("ref_audio_path", ""),
                    "prompt_text": tts_config.get("prompt_text", ""),
                    "prompt_lang": tts_config.get("prompt_lang", "en"),
                },
            )
            if resp.status_code == 200:
                audio_b64 = base64.b64encode(resp.content).decode("ascii")
                await broadcast({"action": "audio", "data": audio_b64})
            else:
                log.warning(f"TTS failed: {resp.status_code} {resp.text[:200]}")
    except Exception:
        log.exception("TTS synthesis error")
