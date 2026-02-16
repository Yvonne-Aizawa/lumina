"""Built-in tool definitions and handlers for the chat system."""

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config as _config
from .config import BuiltinToolsConfig, VectorSearchConfig

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vector search (ChromaDB + Ollama)
# ---------------------------------------------------------------------------

_chroma_collection = None


def init_vector_search(config: VectorSearchConfig):
    """Initialize ChromaDB with Ollama embeddings. Call once at startup."""
    global _chroma_collection
    if not config.enabled:
        return
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

        db_path = _config.STATE_DIR / "vectordb"
        db_path.mkdir(parents=True, exist_ok=True)

        ef = OllamaEmbeddingFunction(
            model_name=config.model,
            url=f"{config.ollama_url.rstrip('/')}",
        )
        client = chromadb.PersistentClient(path=str(db_path))
        _chroma_collection = client.get_or_create_collection(
            config.collection, embedding_function=ef
        )
        log.info(
            f"Vector search initialized: collection={config.collection}, "
            f"model={config.model}, entries={_chroma_collection.count()}"
        )
    except Exception:
        log.exception("Failed to initialize vector search")


def _memories_dir() -> Path:
    return _config.STATE_DIR / "memories"


def _state_path() -> Path:
    return _config.STATE_DIR / "state.json"


def _safe_filename(filename: str) -> Path:
    """Sanitize filename and return the full path in the memories dir."""
    name = filename.removesuffix(".md")
    name = Path(name).name  # strips any directory components
    return _memories_dir() / f"{name}.md"


def _git_commit(message: str):
    """Stage all changes in the state dir and commit with the given message."""
    state_dir = _config.STATE_DIR
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=state_dir,
            check=True,
            capture_output=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", message, "--allow-empty"],
            cwd=state_dir,
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ) as e:
        log.warning(f"Git commit failed in state dir: {e}")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


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
    if tc.vector_search.enabled and _chroma_collection is not None:
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

    return tools


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def handle_memory_create(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")
    if not filename:
        return "Error: filename is required."
    path = _safe_filename(filename)
    if path.exists():
        return f"Memory '{filename}' already exists. Use memory_edit to update it."
    _memories_dir().mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git_commit(f"Added {path.name}")
    return f"Memory '{filename}' created."


def handle_memory_list() -> str:
    _memories_dir().mkdir(exist_ok=True)
    files = sorted(p.stem for p in _memories_dir().glob("*.md"))
    if not files:
        return "No memories found."
    return "Memories:\n" + "\n".join(f"- {f}" for f in files)


def handle_memory_read(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    if not filename:
        return "Error: filename is required."
    path = _safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found."
    return path.read_text(encoding="utf-8")


def handle_memory_edit(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")
    if not filename:
        return "Error: filename is required."
    path = _safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found. Use memory_create to create it."
    path.write_text(content, encoding="utf-8")
    _git_commit(f"Updated {path.name}")
    return f"Memory '{filename}' updated."


def handle_memory_delete(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    if not filename:
        return "Error: filename is required."
    path = _safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found."
    path.unlink()
    _git_commit(f"Deleted {path.name}")
    return f"Memory '{filename}' deleted."


def handle_memory_patch(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    old_string = arguments.get("old_string", "")
    new_string = arguments.get("new_string", "")
    if not filename:
        return "Error: filename is required."
    if not old_string:
        return "Error: old_string is required."
    path = _safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found."
    content = path.read_text(encoding="utf-8")
    count = content.count(old_string)
    if count == 0:
        return f"Error: old_string not found in memory '{filename}'."
    if count > 1:
        return f"Error: old_string matches {count} times in memory '{filename}'. Provide a more specific string."
    content = content.replace(old_string, new_string, 1)
    path.write_text(content, encoding="utf-8")
    _git_commit(f"Updated {path.name}")
    return f"Memory '{filename}' patched."


def _load_state() -> dict:
    if _state_path().exists():
        try:
            return json.loads(_state_path().read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict):
    _state_path().write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def handle_state_set(arguments: dict) -> str:
    key = str(arguments.get("key", "")).strip()
    if not key:
        return "Error: key is required."
    value = arguments.get("value")
    if value == "now":
        value = datetime.now(timezone.utc).isoformat()
    state = _load_state()
    state[key] = value
    _save_state(state)
    return f"State '{key}' set to {json.dumps(value)}."


def handle_state_get(arguments: dict) -> str:
    key = str(arguments.get("key", "")).strip()
    if not key:
        return "Error: key is required."
    state = _load_state()
    if key not in state:
        return f"Key '{key}' not found."
    return f"{key}: {json.dumps(state[key])}"


def handle_state_list() -> str:
    state = _load_state()
    if not state:
        return "State is empty."
    lines = [f"- {k}: {json.dumps(v)}" for k, v in state.items()]
    return "State:\n" + "\n".join(lines)


def handle_state_check_time(arguments: dict) -> str:
    key = arguments.get("key", "").strip()
    if not key:
        return "Error: key is required."
    state = _load_state()
    if key not in state:
        return f"Key '{key}' not found."
    value = state[key]
    try:
        ts = datetime.fromisoformat(value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - ts
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(abs(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        human = " ".join(parts)
        return f"'{key}' was {human} ago ({total_seconds} seconds). Timestamp: {value}"
    except (ValueError, TypeError):
        return f"Error: '{key}' value '{value}' is not a valid timestamp."


async def handle_web_search(arguments: dict, brave_api_key: str) -> str:
    query = arguments.get("query", "").strip()
    if not query:
        return "Error: query is required."
    count = min(int(arguments.get("count", 5)), 20)
    try:
        from brave_search_python_client import BraveSearch, WebSearchRequest

        bs = BraveSearch(api_key=brave_api_key)
        response = await bs.web(WebSearchRequest(q=query, count=count))
        if not response.web or not response.web.results:
            return f"No results found for: {query}"
        lines = []
        for r in response.web.results:
            title = getattr(r, "title", "")
            url = getattr(r, "url", "")
            desc = getattr(r, "description", "")
            lines.append(f"**{title}**\n{url}\n{desc}")
        return "\n\n".join(lines)
    except Exception as e:
        log.exception("Web search error")
        return f"Search error: {e}"


async def handle_run_command(arguments: dict) -> str:
    command = arguments.get("command", "").strip()
    if not command:
        return "Error: command is required."
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace").strip()
        if len(output) > 4000:
            output = output[:4000] + "\n... (truncated)"
        return (
            output
            if output
            else f"Command exited with code {proc.returncode} (no output)."
        )
    except asyncio.TimeoutError:
        proc.kill()
        return "Error: command timed out after 30 seconds."
    except Exception as e:
        return f"Error running command: {e}"


# ---------------------------------------------------------------------------
# Vector search handlers
# ---------------------------------------------------------------------------


def handle_vector_save(arguments: dict) -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    entry_id = arguments.get("id", "").strip()
    content = arguments.get("content", "").strip()
    if not entry_id:
        return "Error: id is required."
    if not content:
        return "Error: content is required."
    metadata = arguments.get("metadata") or {}
    try:
        _chroma_collection.upsert(
            ids=[entry_id], documents=[content], metadatas=[metadata]
        )
        return f"Saved entry '{entry_id}' to vector database."
    except Exception as e:
        return f"Error saving to vector database: {e}"


def handle_vector_search(arguments: dict) -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    query = arguments.get("query", "").strip()
    if not query:
        return "Error: query is required."
    n = min(int(arguments.get("n", 5)), 20)
    try:
        if _chroma_collection.count() == 0:
            return "Vector database is empty."
        results = _chroma_collection.query(query_texts=[query], n_results=n)
        ids = results["ids"][0]
        docs = results["documents"][0]
        distances = (
            results["distances"][0] if results.get("distances") else [None] * len(ids)
        )
        metadatas = (
            results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        )
        if not ids:
            return f"No results found for: {query}"
        lines = []
        for i, (eid, doc, dist, meta) in enumerate(
            zip(ids, docs, distances, metadatas), 1
        ):
            parts = [
                f"**{i}. [{eid}]** (distance: {dist:.4f})"
                if dist is not None
                else f"**{i}. [{eid}]**"
            ]
            if meta:
                parts.append(f"  metadata: {json.dumps(meta)}")
            parts.append(f"  {doc}")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)
    except Exception as e:
        return f"Error searching vector database: {e}"


def handle_vector_delete(arguments: dict) -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    entry_id = arguments.get("id", "").strip()
    if not entry_id:
        return "Error: id is required."
    try:
        _chroma_collection.delete(ids=[entry_id])
        return f"Deleted entry '{entry_id}' from vector database."
    except Exception as e:
        return f"Error deleting from vector database: {e}"


def handle_vector_list() -> str:
    if _chroma_collection is None:
        return "Error: vector search not initialized."
    try:
        result = _chroma_collection.get()
        ids = result["ids"]
        if not ids:
            return "Vector database is empty."
        return f"Vector database entries ({len(ids)}):\n" + "\n".join(
            f"- {eid}" for eid in sorted(ids)
        )
    except Exception as e:
        return f"Error listing vector database: {e}"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


async def handle_tool_call(
    name: str,
    arguments: dict,
    *,
    animation_names: list[str],
    play_animation_fn,
    mcp_manager,
    background_names: list[str] | None = None,
    set_background_fn=None,
    builtin_tools_config: BuiltinToolsConfig | None = None,
) -> str:
    """Execute a tool call and return the result as a string."""
    if name == "get_animations":
        return f"Available animations: {', '.join(animation_names)}"

    if name == "get_backgrounds":
        if background_names:
            return f"Available backgrounds: {', '.join(background_names)}"
        return "No backgrounds available."

    if name == "play_animation":
        anim_name = arguments.get("name", "")
        if anim_name in animation_names:
            await play_animation_fn(anim_name)
            return f"Now playing animation: {anim_name}"
        else:
            return f"Unknown animation: {anim_name}. Available: {', '.join(animation_names)}"

    if name == "memory_list":
        return handle_memory_list()
    if name == "memory_create":
        return handle_memory_create(arguments)
    if name == "memory_read":
        return handle_memory_read(arguments)
    if name == "memory_edit":
        return handle_memory_edit(arguments)
    if name == "memory_delete":
        return handle_memory_delete(arguments)
    if name == "memory_patch":
        return handle_memory_patch(arguments)

    if name == "state_set":
        return handle_state_set(arguments)
    if name == "state_get":
        return handle_state_get(arguments)
    if name == "state_list":
        return handle_state_list()
    if name == "state_check_time":
        return handle_state_check_time(arguments)

    if name == "set_background" and set_background_fn and background_names:
        bg_name = arguments.get("name", "")
        if bg_name in background_names:
            await set_background_fn(bg_name)
            return f"Background changed to: {bg_name}"
        return (
            f"Unknown background: {bg_name}. Available: {', '.join(background_names)}"
        )

    if name == "web_search":
        tc = builtin_tools_config or BuiltinToolsConfig()
        return await handle_web_search(arguments, tc.web_search.brave_api_key)
    if name == "run_command":
        return await handle_run_command(arguments)

    if name == "vector_save":
        return handle_vector_save(arguments)
    if name == "vector_search":
        return handle_vector_search(arguments)
    if name == "vector_delete":
        return handle_vector_delete(arguments)
    if name == "vector_list":
        return handle_vector_list()

    if mcp_manager.has_tool(name):
        return await mcp_manager.call_tool(name, arguments)

    return f"Unknown tool: {name}"
