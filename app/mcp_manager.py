"""MCP client manager — connects to configured MCP servers and exposes their tools."""

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .sandbox import build_sandbox_env, build_wrapper_script

log = logging.getLogger(__name__)

_STDERR_MAX_LINES = 200


class MCPManager:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        # server_name -> ClientSession
        self._sessions: dict[str, ClientSession] = {}
        # tool_name -> (server_name, tool_schema)
        self._tools: dict[str, tuple[str, dict]] = {}

        # --- AI-created server tracking ---
        self._ai_sessions: dict[str, ClientSession] = {}
        self._ai_exit_stacks: dict[str, AsyncExitStack] = {}
        self._ai_stderr_files: dict[str, Path] = {}  # name -> stderr log file
        self._ai_tools: dict[str, list[str]] = {}  # server_name -> [tool_names]

    # ------------------------------------------------------------------
    # Config-defined MCP servers (existing)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # AI-created MCP servers
    # ------------------------------------------------------------------

    async def start_ai_server(
        self,
        name: str,
        server_dir: Path,
        *,
        allow_network: bool = False,
    ) -> list[str]:
        """Start an AI-created MCP server in a sandboxed subprocess.

        Returns list of tool names registered by the server.
        Raises on failure.
        """
        if name in self._ai_sessions:
            raise RuntimeError(f"AI server '{name}' is already running")

        server_py = server_dir / "server.py"
        if not server_py.exists():
            raise FileNotFoundError(f"Server script not found: {server_py}")

        # Ensure sandbox directory exists
        (server_dir / "sandbox").mkdir(parents=True, exist_ok=True)

        # Write the wrapper script
        wrapper_code = build_wrapper_script(server_py, allow_network=allow_network)
        wrapper_path = server_dir / "_wrapper.py"
        wrapper_path.write_text(wrapper_code, encoding="utf-8")

        # Build sandboxed environment
        env = build_sandbox_env(server_dir, allow_network=allow_network)

        # Stderr goes to a log file so we can read it later
        stderr_path = server_dir / "stderr.log"
        self._ai_stderr_files[name] = stderr_path
        stderr_file = open(stderr_path, "w", encoding="utf-8")

        params = StdioServerParameters(
            command=sys.executable,
            args=["-I", str(wrapper_path)],
            env=env,
            cwd=str(server_dir),
        )

        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(
                stdio_client(params, errlog=stderr_file)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception:
            stderr_file.close()
            await stack.aclose()
            raise

        self._ai_exit_stacks[name] = stack
        self._ai_sessions[name] = session

        # Discover tools
        result = await session.list_tools()
        tool_names = []
        for tool in result.tools:
            self._tools[tool.name] = (
                name,
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                },
            )
            tool_names.append(tool.name)
            log.info(f"AI MCP tool registered: {tool.name} (from '{name}')")

        self._ai_tools[name] = tool_names
        return tool_names

    async def stop_ai_server(self, name: str) -> bool:
        """Stop a running AI-created server. Returns True if it was running."""
        if name not in self._ai_sessions:
            return False

        # Remove tools first
        for tool_name in self._ai_tools.pop(name, []):
            self._tools.pop(tool_name, None)

        # Close session and process
        self._ai_sessions.pop(name, None)
        stack = self._ai_exit_stacks.pop(name, None)
        if stack:
            try:
                await stack.aclose()
            except Exception:
                log.exception(f"Error closing AI server '{name}'")

        log.info(f"AI server '{name}' stopped")
        return True

    async def restart_ai_server(
        self,
        name: str,
        server_dir: Path,
        *,
        allow_network: bool = False,
    ) -> list[str]:
        """Stop then start an AI server. Returns new tool names."""
        await self.stop_ai_server(name)
        return await self.start_ai_server(name, server_dir, allow_network=allow_network)

    def get_ai_server_tools(self, name: str) -> list[str]:
        """Return tool names for a specific AI server."""
        return list(self._ai_tools.get(name, []))

    def is_ai_server_running(self, name: str) -> bool:
        return name in self._ai_sessions

    def get_ai_server_logs(self, name: str, lines: int = 50) -> list[str]:
        """Return recent stderr lines from an AI server."""
        stderr_path = self._ai_stderr_files.get(name)
        if stderr_path is None or not stderr_path.exists():
            return []
        try:
            all_lines = stderr_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            return all_lines[-lines:]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Unified tool interface
    # ------------------------------------------------------------------

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
        # Check both config sessions and AI sessions
        session = self._sessions.get(server_name) or self._ai_sessions.get(server_name)
        if session is None:
            return f"Error: MCP server '{server_name}' is not connected"

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
        # Stop AI servers first
        for name in list(self._ai_sessions):
            await self.stop_ai_server(name)
        self._ai_stderr_files.clear()

        # Close config-defined servers
        await self._exit_stack.aclose()
        self._sessions.clear()
        self._tools.clear()
