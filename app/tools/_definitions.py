"""Built-in tool definitions (OpenAI function-calling format)."""

from ..config import BuiltinToolsConfig
from ._vector import get_collection


def get_builtin_tools(
    animation_names: list[str],
    bash_enabled: bool = False,
    background_names: list[str] | None = None,
    builtin_tools_config: BuiltinToolsConfig | None = None,
) -> list[dict]:
    tc = builtin_tools_config or BuiltinToolsConfig()
    tools = []

    # --- Animation group ---
    if tc.animation:
        tools.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "get_animations",
                        "description": "List all available animations for the 3D avatar.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "play_animation",
                        "description": (
                            "Play an animation on the 3D avatar. "
                            "Use this to express emotions or actions visually. "
                            "Call get_animations first if you don't know the available names."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "The animation to play.",
                                }
                            },
                            "required": ["name"],
                        },
                    },
                },
            ]
        )
        if background_names:
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_backgrounds",
                            "description": "List all available background images for the 3D scene.",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "set_background",
                            "description": (
                                "Change the background image of the 3D scene. "
                                "Call get_backgrounds first if you don't know the available names."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "description": "The background image to display.",
                                    }
                                },
                                "required": ["name"],
                            },
                        },
                    },
                ]
            )

    # --- Memory group ---
    if tc.memory:
        # Read-only tools always available
        tools.extend(
            [
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
                        "name": "memory_list",
                        "description": "List all saved memory files by name.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                },
            ]
        )
        # Write tools only when not read-only
        if not tc.memory_readonly:
            tools.extend(
                [
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
                            "name": "memory_patch",
                            "description": "Patch a memory file by replacing a specific substring with new text. Use this for small edits instead of rewriting the whole file.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "filename": {
                                        "type": "string",
                                        "description": "Name of the memory file to patch (without .md extension).",
                                    },
                                    "old_string": {
                                        "type": "string",
                                        "description": "The exact text to find and replace.",
                                    },
                                    "new_string": {
                                        "type": "string",
                                        "description": "The text to replace it with.",
                                    },
                                },
                                "required": ["filename", "old_string", "new_string"],
                            },
                        },
                    },
                ]
            )

    # --- State group ---
    if tc.state:
        tools.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "state_set",
                        "description": "Set a key in the persistent state store. Value can be any type (string, number, boolean, array, object). Use the string 'now' to store the current timestamp.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "description": "The state name / key to set.",
                                },
                                "value": {
                                    "description": "The value to store. Can be any JSON type (string, number, boolean, array, object). Use the string 'now' to store the current timestamp.",
                                },
                            },
                            "required": ["key", "value"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "state_get",
                        "description": "Get a single value from the persistent state store.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "description": "The key to look up.",
                                },
                            },
                            "required": ["key"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "state_list",
                        "description": "List all keys and values in the persistent state store.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "state_check_time",
                        "description": "Check how long ago a timestamp was stored for a key. Returns elapsed time in human-readable form and seconds.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "key": {
                                    "type": "string",
                                    "description": "The key holding a timestamp value.",
                                },
                            },
                            "required": ["key"],
                        },
                    },
                },
            ]
        )

    # --- Web search ---
    if tc.web_search.brave_api_key:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web using Brave Search. Use this to find current information, answer questions about recent events, or look up facts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query.",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of results to return (default 5, max 20).",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )

    # --- Bash ---
    if tc.bash and bash_enabled:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Execute a bash command on the server and return its output.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The bash command to execute.",
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        )

    # --- Vector search group ---
    if tc.vector_search.enabled and get_collection() is not None:
        tools.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "vector_save",
                        "description": "Save text to the vector database for semantic search later. Updates the entry if the ID already exists.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "A unique identifier for this entry.",
                                },
                                "content": {
                                    "type": "string",
                                    "description": "The text content to store and embed.",
                                },
                                "metadata": {
                                    "type": "object",
                                    "description": 'Optional metadata to attach (e.g. {"topic": "hobbies"}).',
                                },
                            },
                            "required": ["id", "content"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "vector_search",
                        "description": "Search the vector database by meaning. Returns the most relevant entries for the query.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query.",
                                },
                                "n": {
                                    "type": "integer",
                                    "description": "Number of results to return (default 5).",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "vector_delete",
                        "description": "Delete an entry from the vector database by ID.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "The ID of the entry to delete.",
                                },
                            },
                            "required": ["id"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "vector_list",
                        "description": "List all entry IDs in the vector database.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
            ]
        )

    # --- MCP server management ---
    if tc.mcp_servers:
        _mcp_create_props = {
            "name": {
                "type": "string",
                "description": "Server name (letters, digits, underscores; must start with a letter).",
            },
            "code": {
                "type": "string",
                "description": "Python source code implementing the MCP server.",
            },
            "description": {
                "type": "string",
                "description": "Short description of what this server does.",
            },
            "auto_start": {
                "type": "boolean",
                "description": "Start immediately and on app restart. Default true.",
            },
        }
        if tc.mcp_servers_allow_network:
            _mcp_create_props["allow_network"] = {
                "type": "boolean",
                "description": "Allow network access (socket, urllib, requests, httpx). Default false.",
            }
        tools.extend(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_create",
                        "description": (
                            "Create a new MCP server from Python code. The server runs in a sandbox. "
                            "Write the code using FastMCP:\n"
                            "```python\n"
                            "from mcp.server.fastmcp import FastMCP\n"
                            'mcp = FastMCP("server-name")\n\n'
                            "@mcp.tool()\n"
                            "def my_tool(param: str) -> str:\n"
                            '    """Tool description."""\n'
                            '    return f"result: {param}"\n\n'
                            "mcp.run()\n"
                            "```\n"
                            "Allowed imports: mcp, json, datetime, math, re, collections, typing, "
                            "dataclasses, enum, time, string, random, itertools, functools, hashlib, "
                            "base64, textwrap, uuid, logging, io. "
                            "For file storage use os.environ['MCP_SANDBOX_DIR'] as the directory path."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": _mcp_create_props,
                            "required": ["name", "code", "description"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_edit",
                        "description": "Update the code of an existing AI-created MCP server. Automatically restarts if running.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Server name.",
                                },
                                "code": {
                                    "type": "string",
                                    "description": "New Python source code.",
                                },
                            },
                            "required": ["name", "code"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_delete",
                        "description": "Delete an AI-created MCP server and all its files.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Server name.",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_list",
                        "description": "List all AI-created MCP servers with their status and tools.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_start",
                        "description": "Start a stopped AI-created MCP server.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Server name.",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_stop",
                        "description": "Stop a running AI-created MCP server.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Server name.",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_server_logs",
                        "description": "Get recent stderr output from an AI-created MCP server for debugging.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Server name.",
                                },
                                "lines": {
                                    "type": "integer",
                                    "description": "Number of recent log lines (default 50, max 200).",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                },
            ]
        )

    return tools
