"""TTS (text-to-speech) synthesis client — supports GPT-SoVITS and Qwen3-TTS."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import TYPE_CHECKING

import httpx

from .broadcast import broadcast

if TYPE_CHECKING:
    from .config import TTSConfig

log = logging.getLogger(__name__)

tts_config: TTSConfig | None = None
_qwen3_model = None


def init_tts(config: TTSConfig):
    """Initialise TTS from the app config. Call once at startup."""
    global tts_config, _qwen3_model
    if not config.enabled:
        return
    tts_config = config

    if config.provider == "qwen3-tts":
        import torch
        from qwen_tts import Qwen3TTSModel

        _qwen3_model = Qwen3TTSModel.from_pretrained(
            config.qwen3_model,
            device_map=config.qwen3_device,
            dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )
        log.info(f"TTS enabled (Qwen3-TTS, model: {config.qwen3_model})")
    else:
        log.info(f"TTS enabled (GPT-SoVITS, server: {config.base_url})")


async def synthesize_and_broadcast(text: str):
    """Synthesize speech and broadcast audio to all clients."""
    if not tts_config or not tts_config.enabled:
        return
    if tts_config.provider == "qwen3-tts":
        await _synthesize_qwen3(text)
    else:
        await _synthesize_gptsovits(text)


async def _synthesize_gptsovits(text: str):
    """Call GPT-SoVITS HTTP API to synthesize speech."""
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


async def _synthesize_qwen3(text: str):
    """Run Qwen3-TTS model locally to synthesize speech."""
    try:
        import soundfile as sf

        loop = asyncio.get_running_loop()
        wavs, sr = await loop.run_in_executor(
            None,
            lambda: _qwen3_model.generate_voice_design(
                text=text,
                language=tts_config.qwen3_language,
                instruct=tts_config.qwen3_instruct,
            ),
        )
        buf = io.BytesIO()
        sf.write(buf, wavs[0], sr, format="WAV")
        audio_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        await broadcast({"action": "audio", "data": audio_b64})
    except Exception:
        log.exception("Qwen3-TTS synthesis error")
