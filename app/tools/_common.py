"""Shared helpers for tool handlers."""

import logging
import subprocess
from pathlib import Path

from .. import config as _config

log = logging.getLogger(__name__)


def memories_dir() -> Path:
    return _config.STATE_DIR / "memories"


def state_path() -> Path:
    return _config.STATE_DIR / "state.json"


def safe_filename(filename: str) -> Path:
    """Sanitize filename and return the full path in the memories dir."""
    name = filename.removesuffix(".md")
    name = Path(name).name  # strips any directory components
    return memories_dir() / f"{name}.md"


def git_commit(message: str):
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
