"""Heartbeat system — periodically prompts the LLM when the user is idle."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .broadcast import broadcast
from .tts import synthesize_and_broadcast

if TYPE_CHECKING:
    from .config import HeartbeatConfig

log = logging.getLogger(__name__)

heartbeat_interval: int = 600
heartbeat_idle_threshold: int = 1200
last_user_interaction: float = 0.0
heartbeat_waiting_for_user: bool = False


def record_user_interaction():
    """Mark the current time as the last user interaction and clear the waiting flag."""
    global last_user_interaction, heartbeat_waiting_for_user
    last_user_interaction = time.monotonic()
    heartbeat_waiting_for_user = False


async def _heartbeat_loop(chat_handler):
    """Periodically prompt the LLM via heartbeat when the user has been idle."""
    global heartbeat_waiting_for_user
    while True:
        await asyncio.sleep(heartbeat_interval)
        if chat_handler is None:
            continue
        if heartbeat_waiting_for_user:
            continue
        idle_time = time.monotonic() - last_user_interaction
        if idle_time < heartbeat_idle_threshold:
            continue
        try:
            await broadcast({"action": "heartbeat", "status": "start"})
            sent = await chat_handler.heartbeat()
            await broadcast({"action": "heartbeat", "status": "end"})
            if sent:
                for text in sent:
                    log.info(f"Heartbeat message: {text[:100]}")
                    await broadcast({"action": "chat", "content": text})
                    await synthesize_and_broadcast(text)
                heartbeat_waiting_for_user = True
        except Exception:
            await broadcast({"action": "heartbeat", "status": "end"})
            log.exception("Heartbeat loop error")


def start_heartbeat(config: HeartbeatConfig, chat_handler) -> asyncio.Task | None:
    """Start the heartbeat background task if enabled. Returns the task or None."""
    global heartbeat_interval, heartbeat_idle_threshold

    if not config.enabled:
        return None

    heartbeat_interval = config.interval
    heartbeat_idle_threshold = config.idle_threshold
    task = asyncio.create_task(_heartbeat_loop(chat_handler))
    log.info(
        f"Heartbeat enabled (interval={heartbeat_interval}s, idle_threshold={heartbeat_idle_threshold}s)"
    )
    return task
