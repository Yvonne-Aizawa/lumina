"""Chat handler — manages conversation, LLM calls, and tool execution."""

import json
import logging

from openai import AsyncOpenAI

from mcp_manager import MCPManager

log = logging.getLogger(__name__)

# Maximum tool-call round-trips before giving up
MAX_TOOL_ROUNDS = 10


class ChatHandler:
    def __init__(
        self,
        llm_config: dict,
        system_prompt: str,
        mcp_manager: MCPManager,
        animation_names: list[str],
        play_animation_fn,
    ):
        self._client = AsyncOpenAI(
            base_url=llm_config["base_url"],
            api_key=llm_config.get("api_key", "unused"),
        )
        self._model = llm_config["model"]
        self._system_prompt = system_prompt
        self._mcp = mcp_manager
        self._animation_names = animation_names
        self._play_animation = play_animation_fn

        # Conversation history (in-memory, single session)
        self._messages: list[dict] = []

    def _get_builtin_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "play_animation",
                    "description": (
                        "Play an animation on the 3D avatar. "
                        "Use this to express emotions or actions visually."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The animation to play.",
                                "enum": self._animation_names,
                            }
                        },
                        "required": ["name"],
                    },
                },
            }
        ]

    def _get_all_tools(self) -> list[dict]:
        return self._get_builtin_tools() + self._mcp.get_openai_tools()

    async def _handle_tool_call(self, name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        if name == "play_animation":
            anim_name = arguments.get("name", "")
            if anim_name in self._animation_names:
                await self._play_animation(anim_name)
                return f"Now playing animation: {anim_name}"
            else:
                return f"Unknown animation: {anim_name}. Available: {', '.join(self._animation_names)}"

        if self._mcp.has_tool(name):
            return await self._mcp.call_tool(name, arguments)

        return f"Unknown tool: {name}"

    async def send_message(self, user_text: str) -> str:
        """Process a user message through the LLM with tool support."""
        self._messages.append({"role": "user", "content": user_text})

        tools = self._get_all_tools()
        messages = [
            {"role": "system", "content": self._system_prompt},
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
                    result = await self._handle_tool_call(fn_name, fn_args)

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
            self._messages.append({"role": "assistant", "content": assistant_text})
            return assistant_text

        # Exhausted tool rounds
        return "I'm having trouble processing that request. Please try again."

    def clear_history(self):
        """Reset conversation history."""
        self._messages.clear()
