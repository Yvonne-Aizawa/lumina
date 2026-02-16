"""Memory tool handlers."""

from ._common import git_commit, memories_dir, safe_filename


def handle_memory_create(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")
    if not filename:
        return "Error: filename is required."
    path = safe_filename(filename)
    if path.exists():
        return f"Memory '{filename}' already exists. Use memory_edit to update it."
    memories_dir().mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git_commit(f"Added {path.name}")
    return f"Memory '{filename}' created."


def handle_memory_list() -> str:
    memories_dir().mkdir(parents=True, exist_ok=True)
    files = sorted(p.stem for p in memories_dir().glob("*.md"))
    if not files:
        return "No memories found."
    return "Memories:\n" + "\n".join(f"- {f}" for f in files)


def handle_memory_read(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    if not filename:
        return "Error: filename is required."
    path = safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found."
    return path.read_text(encoding="utf-8")


def handle_memory_edit(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    content = arguments.get("content", "")
    if not filename:
        return "Error: filename is required."
    path = safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found. Use memory_create to create it."
    path.write_text(content, encoding="utf-8")
    git_commit(f"Updated {path.name}")
    return f"Memory '{filename}' updated."


def handle_memory_delete(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    if not filename:
        return "Error: filename is required."
    path = safe_filename(filename)
    if not path.exists():
        return f"Memory '{filename}' not found."
    path.unlink()
    git_commit(f"Deleted {path.name}")
    return f"Memory '{filename}' deleted."


def handle_memory_patch(arguments: dict) -> str:
    filename = arguments.get("filename", "")
    old_string = arguments.get("old_string", "")
    new_string = arguments.get("new_string", "")
    if not filename:
        return "Error: filename is required."
    if not old_string:
        return "Error: old_string is required."
    path = safe_filename(filename)
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
    git_commit(f"Updated {path.name}")
    return f"Memory '{filename}' patched."
