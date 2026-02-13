"""Heartbeat system — periodically prompts the LLM when the user is idle."""

import asyncio
import logging
import time

from .broadcast import broadcast
from .tts import synthesize_and_broadcast

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_DEFAULT = 600  # seconds (10 minutes)
HEARTBEAT_IDLE_DEFAULT = 1200  # seconds (20 minutes)

heartbeat_interval: int = HEARTBEAT_INTERVAL_DEFAULT
heartbeat_idle_threshold: int = HEARTBEAT_IDLE_DEFAULT
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


def start_heartbeat(config: dict, chat_handler) -> asyncio.Task | None:
    """Start the heartbeat background task if enabled. Returns the task or None."""
    global heartbeat_interval, heartbeat_idle_threshold

    hb_config = config.get("heartbeat", {})
    if not hb_config.get("enabled", False):
        return None

    heartbeat_interval = hb_config.get("interval", HEARTBEAT_INTERVAL_DEFAULT)
    heartbeat_idle_threshold = hb_config.get("idle_threshold", HEARTBEAT_IDLE_DEFAULT)
    task = asyncio.create_task(_heartbeat_loop(chat_handler))
    log.info(
        f"Heartbeat enabled (interval={heartbeat_interval}s, idle_threshold={heartbeat_idle_threshold}s)"
    )
    return task
