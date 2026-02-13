"""STT (speech-to-text) model management, wake word config, and transcription."""

import asyncio
import logging
import tempfile

log = logging.getLogger(__name__)

stt_model = None
stt_enabled: bool = False
stt_language: str | None = None
wakeword_enabled: bool = False
wakeword_keyword: str = "hey_jarvis"


async def init_stt(config: dict):
    """Load the Whisper STT model if enabled in config. Call once at startup."""
    global stt_model, stt_enabled, stt_language

    stt_cfg = config.get("stt", {})
    if not stt_cfg.get("enabled"):
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

        stt_model_size = stt_cfg.get("model", "large-v3")
        stt_device = stt_cfg.get("device", "auto")
        stt_compute = stt_cfg.get("compute_type", "float16")
        log.info(
            f"Loading STT model: {stt_model_size} (device={stt_device}, compute={stt_compute})"
        )
        stt_model = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: WhisperModel(
                stt_model_size, device=stt_device, compute_type=stt_compute
            ),
        )
        stt_enabled = True
        stt_language = stt_cfg.get("language")
        log.info(f"STT model loaded (language={stt_language or 'auto'})")
    except Exception:
        log.exception("Failed to load STT model")


def init_wakeword(config: dict):
    """Load wake word settings from config. Call once at startup."""
    global wakeword_enabled, wakeword_keyword

    ww_cfg = config.get("wakeword", {})
    if ww_cfg.get("enabled"):
        wakeword_enabled = True
        log.info("Wake word enabled")
    if ww_cfg.get("keyword"):
        wakeword_keyword = ww_cfg["keyword"]


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio bytes using the loaded Whisper model. Returns text."""

    def _transcribe():
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, _ = stt_model.transcribe(tmp.name, language=stt_language)
            return "".join(s.text for s in segments).strip()

    return await asyncio.get_event_loop().run_in_executor(None, _transcribe)
