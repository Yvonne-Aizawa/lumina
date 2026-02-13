"""Chat handler — manages conversation, LLM calls, and tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from .mcp_manager import MCPManager
from .tools import get_builtin_tools, handle_tool_call

if TYPE_CHECKING:
    from .config import LLMConfig

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
PROJECT_DIR = Path(__file__).parent.parent
SOUL_DIR = PROJECT_DIR / "state" / "soul"
HEARTBEAT_PATH = SOUL_DIR / "heartbeat.md"
CHATS_DIR = PROJECT_DIR / "state" / "chats"


def load_soul() -> str:
    """Load all markdown files from the soul/ directory into a single system prompt."""
    if not SOUL_DIR.exists():
        return "You are a helpful assistant."
    parts = []
    for path in sorted(SOUL_DIR.glob("*.md")):
        if path == HEARTBEAT_PATH:
            continue
        parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts) if parts else "You are a helpful assistant."


class ChatHandler:
    def __init__(
        self,
        llm_config: LLMConfig,
        mcp_manager: MCPManager,
        animation_names: list[str],
        play_animation_fn,
        notify_tool_call_fn=None,
        brave_api_key: str | None = None,
        bash_enabled: bool = False,
    ):
        self._client = AsyncOpenAI(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
        )
        self._model = llm_config.model
        self._soul = load_soul()
        self._mcp = mcp_manager
        self._animation_names = animation_names
        self._play_animation = play_animation_fn
        self._notify_tool_call = notify_tool_call_fn
        self._brave_api_key = brave_api_key
        self._bash_enabled = bash_enabled

        # Conversation history (in-memory, single session)
        self._messages: list[dict] = []
        self._lock = asyncio.Lock()
        self._chat_id: str | None = None
        self._chat_path: Path | None = None
        self._title: str = ""

        self._new_session()

    # --- Session persistence ---

    def _new_session(self):
        """Start a new chat session."""
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        self._chat_id = now.strftime("%Y-%m-%dT%H-%M-%S")
        self._chat_path = CHATS_DIR / f"{self._chat_id}.json"
        self._title = now.strftime("%b %d, %Y %H:%M")
        self._messages = []

    def _save(self):
        """Persist current session to disk. Skips if no messages yet."""
        if not self._chat_path or not self._messages:
            return
        started_at = self._chat_id
        try:
            parts = self._chat_id.split("T")
            date_part = parts[0]
            time_part = parts[1].replace("-", ":")
            started_at = f"{date_part}T{time_part}+00:00"
        except (IndexError, ValueError):
            pass
        data = {
            "id": self._chat_id,
            "title": self._title,
            "started_at": started_at,
            "messages": self._messages,
        }
        self._chat_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def list_sessions(self) -> list[dict]:
        """Return list of saved sessions, newest first."""
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        sessions = []
        for path in sorted(CHATS_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(
                    {
                        "id": data.get("id", path.stem),
                        "title": data.get("title", ""),
                        "started_at": data.get("started_at", ""),
                        "message_count": len(data.get("messages", [])),
                    }
                )
            except (json.JSONDecodeError, OSError):
                continue
        return sessions

    def load_session(self, chat_id: str) -> list[dict]:
        """Load an existing session by id. Returns the messages."""
        safe_id = Path(chat_id).name  # prevent path traversal
        path = CHATS_DIR / f"{safe_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Chat session '{chat_id}' not found.")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._chat_id = safe_id
        self._chat_path = path
        self._title = data.get("title", "")
        self._messages = data.get("messages", [])
        return self._messages

    @property
    def current_session_id(self) -> str | None:
        return self._chat_id

    # --- Tools ---

    def _get_all_tools(self) -> list[dict]:
        return (
            get_builtin_tools(
                self._animation_names, self._brave_api_key, self._bash_enabled
            )
            + self._mcp.get_openai_tools()
        )

    async def _dispatch_tool(self, name: str, arguments: dict) -> str:
        return await handle_tool_call(
            name,
            arguments,
            animation_names=self._animation_names,
            play_animation_fn=self._play_animation,
            brave_api_key=self._brave_api_key,
            mcp_manager=self._mcp,
        )

    # --- Chat ---

    async def send_message(self, user_text: str) -> str:
        """Process a user message through the LLM with tool support."""
        async with self._lock:
            self._messages.append({"role": "user", "content": user_text})
            self._save()

            tools = self._get_all_tools()
            llm_messages = [m for m in self._messages if m["role"] != "tool_call"]
            messages = [
                {"role": "system", "content": self._soul},
                *llm_messages,
            ]

        for _ in range(MAX_TOOL_ROUNDS):
            kwargs = {"model": self._model, "messages": messages}
            if tools:
                kwargs["tools"] = tools

            response = await self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
                # Add assistant message with tool calls
                messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    log.info(f"Tool call: {fn_name}({fn_args})")
                    async with self._lock:
                        self._messages.append(
                            {"role": "tool_call", "name": fn_name, "arguments": fn_args}
                        )
                        self._save()
                    if self._notify_tool_call:
                        await self._notify_tool_call(fn_name, fn_args)
                    result = await self._dispatch_tool(fn_name, fn_args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

                # Continue loop — LLM will process tool results
                continue

            # No tool calls — we have a final text response
            assistant_text = choice.message.content or ""
            async with self._lock:
                self._messages.append({"role": "assistant", "content": assistant_text})
                self._save()
            return assistant_text

        # Exhausted tool rounds
        return "I'm having trouble processing that request. Please try again."

    # --- Heartbeat ---

    def _get_heartbeat_tools(self) -> list[dict]:
        """Tools available during heartbeat — includes a send_message tool."""
        return self._get_all_tools() + [
            {
                "type": "function",
                "function": {
                    "name": "send_message",
                    "description": (
                        "Send a message to the user. Only call this if you "
                        "have something meaningful to say."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The message to send to the user.",
                            }
                        },
                        "required": ["text"],
                    },
                },
            },
        ]

    async def heartbeat(self) -> str | None:
        """Run a background heartbeat prompt. Returns message text only if AI chose to send one."""
        if not HEARTBEAT_PATH.exists():
            return None
        heartbeat_prompt = HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
        if not heartbeat_prompt:
            return None

        messages = [
            {"role": "system", "content": self._soul},
            {"role": "user", "content": heartbeat_prompt},
        ]

        tools = self._get_heartbeat_tools()
        kwargs = {"model": self._model, "messages": messages, "tools": tools}
        sent_messages: list[str] = []

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = await self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]

                if not (
                    choice.finish_reason == "tool_calls" or choice.message.tool_calls
                ):
                    break

                messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    if fn_name == "send_message":
                        text = fn_args.get("text", "").strip()
                        if text:
                            sent_messages.append(text)
                            log.info(f"Heartbeat send_message: {text[:100]}")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": "Message sent.",
                            }
                        )
                    else:
                        log.info(f"Heartbeat tool call: {fn_name}({fn_args})")
                        result = await self._dispatch_tool(fn_name, fn_args)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result,
                            }
                        )

                kwargs["messages"] = messages

        except Exception:
            log.exception("Heartbeat error")

        if sent_messages:
            async with self._lock:
                for text in sent_messages:
                    self._messages.append({"role": "assistant", "content": text})
                self._save()
        return sent_messages or None

    def clear_history(self):
        """Start a new chat session (old session stays on disk)."""
        self._new_session()
