"""Chat handler — manages conversation, LLM calls, and tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from .mcp_manager import MCPManager
from .tools import get_builtin_tools, handle_tool_call

if TYPE_CHECKING:
    from .config import LLMConfig

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
SOUL_DIR = Path(__file__).parent.parent / "state" / "soul"
HEARTBEAT_PATH = SOUL_DIR / "heartbeat.md"


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

    async def send_message(self, user_text: str) -> str:
        """Process a user message through the LLM with tool support."""
        async with self._lock:
            self._messages.append({"role": "user", "content": user_text})

            tools = self._get_all_tools()
            messages = [
                {"role": "system", "content": self._soul},
                *self._messages,
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
            return assistant_text

        # Exhausted tool rounds
        return "I'm having trouble processing that request. Please try again."

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
        return sent_messages or None

    def clear_history(self):
        """Reset conversation history."""
        self._messages.clear()
