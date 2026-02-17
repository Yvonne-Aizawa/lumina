"""Speech-to-text route handlers."""

import logging

from fastapi import APIRouter, Depends, UploadFile

from .. import wakeword
from ..auth import require_auth
from ..stt import is_enabled as stt_is_enabled
from ..stt import transcribe

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/stt/status", dependencies=[Depends(require_auth)])
async def api_stt_status():
    return {
        "enabled": stt_is_enabled(),
        "wakeword": wakeword.get_keyword(),
        "wakeword_enabled": wakeword.is_enabled(),
        "wakeword_auto_start": wakeword.is_auto_start(),
    }


@router.post("/api/transcribe", dependencies=[Depends(require_auth)])
async def api_transcribe(file: UploadFile):
    if not stt_is_enabled():
        return {"error": "STT not enabled"}
    try:
        audio_bytes = await file.read()
        text = await transcribe(audio_bytes)
        return {"text": text}
    except Exception as e:
        log.exception("STT transcription error")
        return {"error": str(e)}
