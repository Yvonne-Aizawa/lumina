"""MCP client manager — connects to configured MCP servers and exposes their tools."""

import asyncio
import logging
import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger(__name__)


class MCPManager:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        # server_name -> ClientSession
        self._sessions: dict[str, ClientSession] = {}
        # tool_name -> (server_name, tool_schema)
        self._tools: dict[str, tuple[str, dict]] = {}

    async def start(self, mcp_servers: dict):
        """Connect to all configured MCP servers and collect their tools."""
        for name, config in mcp_servers.items():
            try:
                await self._connect_server(name, config)
            except Exception:
                log.exception(f"Failed to connect to MCP server '{name}'")

    async def _connect_server(self, name: str, config: dict):
        # Merge custom env vars with current environment so PATH etc. are preserved
        env = None
        if config.get("env"):
            env = {**os.environ, **config["env"]}

        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env=env,
        )
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._sessions[name] = session

        # Collect tools
        result = await session.list_tools()
        for tool in result.tools:
            self._tools[tool.name] = (
                name,
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                },
            )
            log.info(f"MCP tool registered: {tool.name} (from '{name}')")

    def get_openai_tools(self) -> list[dict]:
        """Return all MCP tools in OpenAI function-calling format."""
        tools = []
        for tool_name, (_, schema) in self._tools.items():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": schema["name"],
                        "description": schema["description"],
                        "parameters": schema["input_schema"],
                    },
                }
            )
        return tools

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool on the appropriate MCP server, return the text result."""
        if name not in self._tools:
            return f"Error: unknown MCP tool '{name}'"

        server_name, _ = self._tools[name]
        session = self._sessions[server_name]

        result = await session.call_tool(name, arguments=arguments)

        # Extract text from result content
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            else:
                parts.append(str(content))
        return "\n".join(parts) if parts else "Tool returned no output."

    async def shutdown(self):
        """Close all MCP server connections."""
        await self._exit_stack.aclose()
        self._sessions.clear()
        self._tools.clear()
