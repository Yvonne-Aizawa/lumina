"""Configuration loading and path constants."""

import json
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
ASSETS_DIR = PROJECT_DIR / "assets"
ANIMS_DIR = ASSETS_DIR / "anims"
MODELS_DIR = ASSETS_DIR / "models"
CONFIG_PATH = PROJECT_DIR / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"llm": {}, "system_prompt": "", "mcp_servers": {}}
