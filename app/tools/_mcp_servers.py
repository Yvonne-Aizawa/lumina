"""AI-created MCP server management tool handlers."""

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .. import config as _config
from ..sandbox import validate_code
from ._common import git_commit

log = logging.getLogger(__name__)


def _servers_dir() -> Path:
    d = _config.STATE_DIR / "mcp_servers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path() -> Path:
    return _servers_dir() / "manifest.json"


def _load_manifest() -> dict:
    p = _manifest_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_manifest(manifest: dict) -> None:
    _manifest_path().write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _safe_name(name: str) -> str:
    """Validate and return a safe server name."""
    name = name.strip()
    if not name:
        raise ValueError("Server name is required")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", name):
        raise ValueError(
            "Server name must start with a letter and contain only "
            "letters, digits, and underscores"
        )
    if len(name) > 64:
        raise ValueError("Server name must be 64 characters or less")
    return name


async def handle_mcp_server_create(
    arguments: dict, mcp_manager, *, network_allowed: bool = False
) -> str:
    try:
        name = _safe_name(arguments.get("name", ""))
    except ValueError as e:
        return f"Error: {e}"

    code = arguments.get("code", "").strip()
    if not code:
        return "Error: code is required."

    description = arguments.get("description", "")
    allow_network = bool(arguments.get("allow_network", False)) and network_allowed
    auto_start = bool(arguments.get("auto_start", True))

    # Check if already exists
    server_dir = _servers_dir() / name
    if server_dir.exists():
        return (
            f"Error: server '{name}' already exists. Use mcp_server_edit to update it."
        )

    # Validate code
    ok, err = validate_code(code, allow_network=allow_network)
    if not ok:
        return f"Code validation failed: {err}"

    # Create server directory and files
    server_dir.mkdir(parents=True, exist_ok=True)
    (server_dir / "sandbox").mkdir(exist_ok=True)
    (server_dir / "server.py").write_text(code, encoding="utf-8")

    # Update manifest
    manifest = _load_manifest()
    now = datetime.now(timezone.utc).isoformat()
    manifest[name] = {
        "description": description,
        "allow_network": allow_network,
        "auto_start": auto_start,
        "created_at": now,
        "modified_at": now,
    }
    _save_manifest(manifest)
    git_commit(f"Created MCP server: {name}")

    # Start if requested
    if auto_start:
        try:
            tools = await mcp_manager.start_ai_server(
                name, server_dir, allow_network=allow_network
            )
            return (
                f"Server '{name}' created and started. "
                f"Tools: {', '.join(tools) if tools else 'none'}"
            )
        except Exception as e:
            return f"Server '{name}' created but failed to start: {e}"

    return f"Server '{name}' created (not started)."


async def handle_mcp_server_edit(arguments: dict, mcp_manager) -> str:
    try:
        name = _safe_name(arguments.get("name", ""))
    except ValueError as e:
        return f"Error: {e}"

    code = arguments.get("code", "").strip()
    if not code:
        return "Error: code is required."

    server_dir = _servers_dir() / name
    if not server_dir.exists():
        return f"Error: server '{name}' does not exist."

    manifest = _load_manifest()
    meta = manifest.get(name, {})
    allow_network = meta.get("allow_network", False)

    # Validate new code
    ok, err = validate_code(code, allow_network=allow_network)
    if not ok:
        return f"Code validation failed: {err}"

    # Stop if running
    was_running = mcp_manager.is_ai_server_running(name)
    if was_running:
        await mcp_manager.stop_ai_server(name)

    # Write new code
    (server_dir / "server.py").write_text(code, encoding="utf-8")
    meta["modified_at"] = datetime.now(timezone.utc).isoformat()
    manifest[name] = meta
    _save_manifest(manifest)
    git_commit(f"Updated MCP server: {name}")

    # Restart if it was running
    if was_running:
        try:
            tools = await mcp_manager.start_ai_server(
                name, server_dir, allow_network=allow_network
            )
            return (
                f"Server '{name}' updated and restarted. "
                f"Tools: {', '.join(tools) if tools else 'none'}"
            )
        except Exception as e:
            return f"Server '{name}' updated but failed to restart: {e}"

    return f"Server '{name}' updated (not running)."


async def handle_mcp_server_delete(arguments: dict, mcp_manager) -> str:
    try:
        name = _safe_name(arguments.get("name", ""))
    except ValueError as e:
        return f"Error: {e}"

    server_dir = _servers_dir() / name
    if not server_dir.exists():
        return f"Error: server '{name}' does not exist."

    # Stop if running
    await mcp_manager.stop_ai_server(name)

    # Remove files
    shutil.rmtree(server_dir)

    # Update manifest
    manifest = _load_manifest()
    manifest.pop(name, None)
    _save_manifest(manifest)
    git_commit(f"Deleted MCP server: {name}")

    return f"Server '{name}' deleted."


async def handle_mcp_server_list(mcp_manager) -> str:
    manifest = _load_manifest()
    if not manifest:
        return "No AI-created MCP servers."

    lines = []
    for name, meta in sorted(manifest.items()):
        running = mcp_manager.is_ai_server_running(name)
        tools = mcp_manager.get_ai_server_tools(name) if running else []
        status = "running" if running else "stopped"
        desc = meta.get("description", "")
        parts = [f"**{name}** [{status}]"]
        if desc:
            parts.append(f"  {desc}")
        if tools:
            parts.append(f"  Tools: {', '.join(tools)}")
        lines.append("\n".join(parts))

    return "\n\n".join(lines)


async def handle_mcp_server_start(arguments: dict, mcp_manager) -> str:
    try:
        name = _safe_name(arguments.get("name", ""))
    except ValueError as e:
        return f"Error: {e}"

    if mcp_manager.is_ai_server_running(name):
        return f"Server '{name}' is already running."

    server_dir = _servers_dir() / name
    if not server_dir.exists():
        return f"Error: server '{name}' does not exist."

    manifest = _load_manifest()
    meta = manifest.get(name, {})
    allow_network = meta.get("allow_network", False)

    try:
        tools = await mcp_manager.start_ai_server(
            name, server_dir, allow_network=allow_network
        )
        return (
            f"Server '{name}' started. Tools: {', '.join(tools) if tools else 'none'}"
        )
    except Exception as e:
        return f"Failed to start server '{name}': {e}"


async def handle_mcp_server_stop(arguments: dict, mcp_manager) -> str:
    try:
        name = _safe_name(arguments.get("name", ""))
    except ValueError as e:
        return f"Error: {e}"

    if not mcp_manager.is_ai_server_running(name):
        return f"Server '{name}' is not running."

    await mcp_manager.stop_ai_server(name)
    return f"Server '{name}' stopped."


async def handle_mcp_server_logs(arguments: dict, mcp_manager) -> str:
    try:
        name = _safe_name(arguments.get("name", ""))
    except ValueError as e:
        return f"Error: {e}"

    lines_count = min(int(arguments.get("lines", 50)), 200)
    lines = mcp_manager.get_ai_server_logs(name, lines_count)
    if not lines:
        return f"No logs for server '{name}'."
    return "\n".join(lines)


async def start_servers_from_manifest(mcp_manager) -> None:
    """Auto-start AI servers marked with auto_start=true. Called at app startup."""
    manifest = _load_manifest()
    for name, meta in manifest.items():
        if not meta.get("auto_start", False):
            continue
        server_dir = _servers_dir() / name
        if not (server_dir / "server.py").exists():
            log.warning(
                f"AI server '{name}' in manifest but server.py missing, skipping"
            )
            continue
        try:
            allow_network = meta.get("allow_network", False)
            tools = await mcp_manager.start_ai_server(
                name, server_dir, allow_network=allow_network
            )
            log.info(f"Auto-started AI server '{name}': tools={tools}")
        except Exception:
            log.exception(f"Failed to auto-start AI server '{name}'")
