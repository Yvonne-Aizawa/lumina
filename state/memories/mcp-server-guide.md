# MCP Server Guide

Use `mcp_server_create` to build custom tool servers. Each server runs in a sandboxed Python subprocess.

## Template

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server-name")

@mcp.tool()
def tool_name(param: str) -> str:
    """Describe what this tool does. This becomes the tool description the LLM sees."""
    return f"result: {param}"

mcp.run()
```

**Every server must** call `mcp.run()` at the end.

## Type hints

FastMCP uses type hints to build the tool schema. Always annotate parameters and return types:

```python
@mcp.tool()
def search(query: str, limit: int = 5) -> str:
    """Search for something."""
    ...
```

- Use `str`, `int`, `float`, `bool` for simple params
- Optional params need defaults
- Always return `str` (the LLM reads the output as text)

## File storage

Each server has a sandbox directory for reading/writing files:

```python
import os
import json

SANDBOX = os.environ["MCP_SANDBOX_DIR"]

@mcp.tool()
def save(key: str, value: str) -> str:
    """Save a value to a file."""
    path = os.path.join(SANDBOX, f"{key}.json")
    with open(path, "w") as f:
        json.dump({"value": value}, f)
    return f"Saved {key}"

@mcp.tool()
def load(key: str) -> str:
    """Load a value from a file."""
    path = os.path.join(SANDBOX, f"{key}.json")
    if not os.path.exists(path):
        return f"{key} not found"
    with open(path) as f:
        data = json.load(f)
    return data["value"]
```

**Important:** `os` is blocked by the sandbox, but `os.environ` and `os.path` work inside the wrapper. Only use `os.environ["MCP_SANDBOX_DIR"]` and `os.path` for file paths -- no `os.system`, `os.listdir`, etc.

## Allowed imports

```
mcp, json, datetime, math, re, collections, typing, dataclasses,
enum, time, string, random, itertools, functools, hashlib, base64,
textwrap, uuid, decimal, fractions, statistics, operator, copy,
pprint, io, struct, abc, contextlib, logging
```

Network modules (`socket`, `urllib`, `requests`, `httpx`) require `allow_network=true`.

Everything else is blocked (no `os`, `subprocess`, `shutil`, `sys`, `pathlib`).

## Examples

### Calculator

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("calculator")

@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a math expression safely. Supports +, -, *, /, **, parentheses."""
    allowed = set("0123456789.+-*/() ")
    if not all(c in allowed for c in expression):
        return "Error: only numbers and +-*/() are allowed"
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error: {e}"

mcp.run()
```

### Note-taker with persistence

```python
from mcp.server.fastmcp import FastMCP
import os
import json

mcp = FastMCP("notes")
SANDBOX = os.environ["MCP_SANDBOX_DIR"]
NOTES_FILE = os.path.join(SANDBOX, "notes.json")

def _load_notes() -> dict:
    if not os.path.exists(NOTES_FILE):
        return {}
    with open(NOTES_FILE) as f:
        return json.load(f)

def _save_notes(notes: dict):
    with open(NOTES_FILE, "w") as f:
        json.dump(notes, f, indent=2)

@mcp.tool()
def add_note(title: str, content: str) -> str:
    """Add a note with a title and content."""
    notes = _load_notes()
    notes[title] = content
    _save_notes(notes)
    return f"Note '{title}' saved."

@mcp.tool()
def get_note(title: str) -> str:
    """Get a note by title."""
    notes = _load_notes()
    if title not in notes:
        return f"Note '{title}' not found. Available: {', '.join(notes.keys()) or 'none'}"
    return notes[title]

@mcp.tool()
def list_notes() -> str:
    """List all note titles."""
    notes = _load_notes()
    if not notes:
        return "No notes yet."
    return "\n".join(f"- {title}" for title in sorted(notes))

@mcp.tool()
def delete_note(title: str) -> str:
    """Delete a note by title."""
    notes = _load_notes()
    if title not in notes:
        return f"Note '{title}' not found."
    del notes[title]
    _save_notes(notes)
    return f"Note '{title}' deleted."

mcp.run()
```

### Random utilities

```python
from mcp.server.fastmcp import FastMCP
import random
import hashlib
import uuid
import datetime

mcp = FastMCP("utils")

@mcp.tool()
def roll_dice(sides: int = 6, count: int = 1) -> str:
    """Roll dice. Returns the results and total."""
    rolls = [random.randint(1, sides) for _ in range(count)]
    return f"Rolls: {rolls}, Total: {sum(rolls)}"

@mcp.tool()
def generate_uuid() -> str:
    """Generate a random UUID."""
    return str(uuid.uuid4())

@mcp.tool()
def hash_text(text: str, algorithm: str = "sha256") -> str:
    """Hash text with the given algorithm (md5, sha1, sha256)."""
    if algorithm not in ("md5", "sha1", "sha256"):
        return "Supported algorithms: md5, sha1, sha256"
    h = hashlib.new(algorithm, text.encode())
    return h.hexdigest()

@mcp.tool()
def timestamp() -> str:
    """Get the current UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

mcp.run()
```

## Management

- `mcp_server_list` -- see all servers and their status
- `mcp_server_start` / `mcp_server_stop` -- control running servers
- `mcp_server_edit` -- update code (auto-restarts if running)
- `mcp_server_delete` -- remove a server
- `mcp_server_logs` -- check stderr output for debugging errors

## Tips

- Keep servers focused -- one server per domain (calculator, notes, etc.)
- Write clear tool descriptions -- they are what you see when deciding which tool to use
- Return strings from all tools -- format results as readable text
- Use the sandbox dir for any files -- data persists across restarts
- Check logs if a server fails to start -- usually a syntax or import error
