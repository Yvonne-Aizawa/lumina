"""Chat route handlers."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_auth
from ..broadcast import set_expression
from ..emotion import detect_emotion
from ..heartbeat import record_user_interaction
from ..tts import synthesize_and_broadcast

log = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatLoadRequest(BaseModel):
    id: str


@router.post("/api/chat", dependencies=[Depends(require_auth)])
async def api_chat(req: ChatRequest):
    from ..server import chat_handler

    record_user_interaction()
    if chat_handler is None:
        return {"error": "Chat not initialized"}
    try:
        response = await chat_handler.send_message(req.message)
        if response:
            expression = await detect_emotion(response)
            if expression:
                await set_expression(expression)
            asyncio.create_task(synthesize_and_broadcast(response))
        return {"response": response}
    except Exception as e:
        log.exception("Chat error")
        return {"error": str(e)}


@router.post("/api/chat/clear", dependencies=[Depends(require_auth)])
async def api_chat_clear():
    from ..server import chat_handler

    if chat_handler:
        chat_handler.clear_history()
    return {"status": "ok"}


@router.get("/api/chats", dependencies=[Depends(require_auth)])
async def api_chats():
    from ..server import chat_handler

    if chat_handler is None:
        return {"sessions": []}
    return {
        "sessions": chat_handler.list_sessions(),
        "current": chat_handler.current_session_id,
    }


@router.post("/api/chats/new", dependencies=[Depends(require_auth)])
async def api_chats_new():
    from ..server import chat_handler

    if chat_handler is None:
        return {"error": "Chat not initialized"}
    chat_handler.clear_history()
    return {"status": "ok", "id": chat_handler.current_session_id}


@router.post("/api/chats/load", dependencies=[Depends(require_auth)])
async def api_chats_load(req: ChatLoadRequest):
    from ..server import chat_handler

    if chat_handler is None:
        return {"error": "Chat not initialized"}
    try:
        messages = chat_handler.load_session(req.id)
        return {"status": "ok", "id": req.id, "messages": messages}
    except FileNotFoundError as e:
        return {"error": str(e)}
