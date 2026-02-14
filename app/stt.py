"""STT (speech-to-text) model management, wake word config, and transcription."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import STTConfig

log = logging.getLogger(__name__)

stt_model = None
stt_enabled: bool = False
stt_language: str | None = None


async def init_stt(config: STTConfig):
    """Load the Whisper STT model if enabled in config. Call once at startup."""
    global stt_model, stt_enabled, stt_language

    if not config.enabled:
        return

    try:
        # Ensure pip-installed NVIDIA libs are discoverable
        try:
            import os

            import nvidia.cublas
            import nvidia.cudnn

            for pkg in (nvidia.cublas, nvidia.cudnn):
                lib_dir = os.path.join(pkg.__path__[0], "lib")
                if lib_dir not in os.environ.get("LD_LIBRARY_PATH", ""):
                    os.environ["LD_LIBRARY_PATH"] = (
                        lib_dir + ":" + os.environ.get("LD_LIBRARY_PATH", "")
                    )
                    import ctypes

                    for lib in os.listdir(lib_dir):
                        if lib.endswith(".so") or ".so." in lib:
                            try:
                                ctypes.cdll.LoadLibrary(os.path.join(lib_dir, lib))
                            except OSError:
                                pass
        except ImportError:
            pass

        from faster_whisper import WhisperModel

        log.info(
            f"Loading STT model: {config.model} (device={config.device}, compute={config.compute_type})"
        )
        stt_model = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: WhisperModel(
                config.model, device=config.device, compute_type=config.compute_type
            ),
        )
        stt_enabled = True
        stt_language = config.language
        log.info(f"STT model loaded (language={stt_language or 'auto'})")
    except Exception:
        log.exception("Failed to load STT model")


# Common Whisper hallucinations on silence/quiet audio (from YouTube training data)
HALLUCINATION_PHRASES = {
    "thank you for watching",
    "thanks for watching",
    "thank you for listening",
    "thanks for listening",
    "subscribe",
    "like and subscribe",
    "please subscribe",
    "thank you",
    "thanks",
    "bye",
    "goodbye",
    "see you next time",
    "see you in the next video",
    "you",
}


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio bytes using the loaded Whisper model. Returns text."""

    def _transcribe():
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, _ = stt_model.transcribe(tmp.name, language=stt_language)
            text = "".join(s.text for s in segments).strip()
            # Filter out Whisper hallucinations on silence
            if text.lower().rstrip(".!,") in HALLUCINATION_PHRASES:
                return ""
            return text

    return await asyncio.get_event_loop().run_in_executor(None, _transcribe)
