"""Chat handler — manages conversation, LLM calls, and tool execution."""

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from mcp_manager import MCPManager

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
BASE_DIR = Path(__file__).parent
MEMORIES_DIR = BASE_DIR / "memories"
SOUL_DIR = BASE_DIR / "soul"


def load_soul() -> str:
    """Load all markdown files from the soul/ directory into a single system prompt."""
    if not SOUL_DIR.exists():
        return "You are a helpful assistant."
    parts = []
    for path in sorted(SOUL_DIR.glob("*.md")):
        parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts) if parts else "You are a helpful assistant."


class ChatHandler:
    def __init__(
        self,
        llm_config: dict,
        mcp_manager: MCPManager,
        animation_names: list[str],
        play_animation_fn,
    ):
        self._client = AsyncOpenAI(
            base_url=llm_config["base_url"],
            api_key=llm_config.get("api_key", "unused"),
        )
        self._model = llm_config["model"]
        self._soul = load_soul()
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
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_create",
                    "description": "Create a new memory as a markdown file. Use this to remember important information about the user or conversations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Name for the memory file (without .md extension).",
                            },
                            "content": {
                                "type": "string",
                                "description": "Markdown content to write to the memory file.",
                            },
                        },
                        "required": ["filename", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_read",
                    "description": "Read a memory file. Use this to recall previously stored information.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Name of the memory file to read (without .md extension). Use 'all' to list all memory files.",
                            },
                        },
                        "required": ["filename"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_edit",
                    "description": "Edit an existing memory file by replacing its content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Name of the memory file to edit (without .md extension).",
                            },
                            "content": {
                                "type": "string",
                                "description": "New markdown content for the memory file.",
                            },
                        },
                        "required": ["filename", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_delete",
                    "description": "Delete a memory file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Name of the memory file to delete (without .md extension).",
                            },
                        },
                        "required": ["filename"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_list",
                    "description": "List all saved memory files by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]

    def _get_all_tools(self) -> list[dict]:
        return self._get_builtin_tools() + self._mcp.get_openai_tools()

    def _safe_filename(self, filename: str) -> Path:
        """Sanitize filename and return the full path in the memories dir."""
        # Strip .md if provided, sanitize to prevent path traversal
        name = filename.removesuffix(".md")
        name = Path(name).name  # strips any directory components
        return MEMORIES_DIR / f"{name}.md"

    def _handle_memory_create(self, arguments: dict) -> str:
        filename = arguments.get("filename", "")
        content = arguments.get("content", "")
        if not filename:
            return "Error: filename is required."
        path = self._safe_filename(filename)
        if path.exists():
            return f"Memory '{filename}' already exists. Use memory_edit to update it."
        MEMORIES_DIR.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Memory '{filename}' created."

    def _handle_memory_list(self) -> str:
        MEMORIES_DIR.mkdir(exist_ok=True)
        files = sorted(p.stem for p in MEMORIES_DIR.glob("*.md"))
        if not files:
            return "No memories found."
        return "Memories:\n" + "\n".join(f"- {f}" for f in files)

    def _handle_memory_read(self, arguments: dict) -> str:
        filename = arguments.get("filename", "")
        if not filename:
            return "Error: filename is required."
        path = self._safe_filename(filename)
        if not path.exists():
            return f"Memory '{filename}' not found."
        return path.read_text(encoding="utf-8")

    def _handle_memory_edit(self, arguments: dict) -> str:
        filename = arguments.get("filename", "")
        content = arguments.get("content", "")
        if not filename:
            return "Error: filename is required."
        path = self._safe_filename(filename)
        if not path.exists():
            return f"Memory '{filename}' not found. Use memory_create to create it."
        path.write_text(content, encoding="utf-8")
        return f"Memory '{filename}' updated."

    def _handle_memory_delete(self, arguments: dict) -> str:
        filename = arguments.get("filename", "")
        if not filename:
            return "Error: filename is required."
        path = self._safe_filename(filename)
        if not path.exists():
            return f"Memory '{filename}' not found."
        path.unlink()
        return f"Memory '{filename}' deleted."

    async def _handle_tool_call(self, name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        if name == "play_animation":
            anim_name = arguments.get("name", "")
            if anim_name in self._animation_names:
                await self._play_animation(anim_name)
                return f"Now playing animation: {anim_name}"
            else:
                return f"Unknown animation: {anim_name}. Available: {', '.join(self._animation_names)}"

        if name == "memory_list":
            return self._handle_memory_list()
        if name == "memory_create":
            return self._handle_memory_create(arguments)
        if name == "memory_read":
            return self._handle_memory_read(arguments)
        if name == "memory_edit":
            return self._handle_memory_edit(arguments)
        if name == "memory_delete":
            return self._handle_memory_delete(arguments)

        if self._mcp.has_tool(name):
            return await self._mcp.call_tool(name, arguments)

        return f"Unknown tool: {name}"

    async def send_message(self, user_text: str) -> str:
        """Process a user message through the LLM with tool support."""
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
