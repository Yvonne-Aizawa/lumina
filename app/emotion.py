"""Emotion detection using HuggingFace transformers."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import EmotionConfig

log = logging.getLogger(__name__)

_pipeline = None

# Map model labels to VRM expression names
EMOTION_TO_VRM = {
    "joy": "happy",
    "sadness": "sad",
    "anger": "angry",
    "surprise": "surprised",
    "fear": "surprised",
    "disgust": "angry",
    "neutral": "neutral",
}


def init_emotion(config: EmotionConfig):
    """Load the emotion classification pipeline. Call once at startup."""
    global _pipeline
    if not config.enabled:
        return
    try:
        from transformers import pipeline

        _pipeline = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base",
            top_k=1,
        )
        log.info("Emotion detection enabled")
    except Exception:
        log.exception("Failed to initialize emotion detection")


async def detect_emotion(text: str) -> str | None:
    """Detect the dominant emotion and return the VRM expression name."""
    if _pipeline is None:
        return None
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _pipeline, text[:512])
        label = result[0][0]["label"]
        expression = EMOTION_TO_VRM.get(label)
        log.info(f"Emotion: {label} -> expression: {expression}")
        return expression
    except Exception:
        log.exception("Emotion detection error")
        return None
