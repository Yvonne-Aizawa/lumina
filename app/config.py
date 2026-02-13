"""Configuration loading and path constants."""

import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
ASSETS_DIR = PROJECT_DIR / "assets"
ANIMS_DIR = ASSETS_DIR / "anims"
MODELS_DIR = ASSETS_DIR / "models"
CONFIG_PATH = PROJECT_DIR / "config.json"


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "unused"
    model: str = "default"


@dataclass
class STTConfig:
    enabled: bool = False
    model: str = "large-v3"
    device: str = "auto"
    compute_type: str = "float16"
    language: str | None = None


@dataclass
class WakeWordConfig:
    enabled: bool = False
    keyword: str = "hey_jarvis"
    model_file: str | None = None


@dataclass
class TTSConfig:
    enabled: bool = False
    base_url: str = "http://localhost:9880"
    ref_audio_path: str = ""
    prompt_text: str = ""
    prompt_lang: str = "en"
    text_lang: str = "en"


@dataclass
class HeartbeatConfig:
    enabled: bool = False
    interval: int = 600
    idle_threshold: int = 1200


@dataclass
class BraveConfig:
    enabled: bool = False
    api_key: str | None = None


@dataclass
class BashConfig:
    enabled: bool = False


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    wakeword: WakeWordConfig = field(default_factory=WakeWordConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    brave: BraveConfig = field(default_factory=BraveConfig)
    bash: BashConfig = field(default_factory=BashConfig)
    mcp_servers: dict[str, dict] = field(default_factory=dict)


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    raw = json.loads(CONFIG_PATH.read_text())
    return Config(
        llm=LLMConfig(**raw.get("llm", {})),
        stt=STTConfig(**raw.get("stt", {})),
        wakeword=WakeWordConfig(**raw.get("wakeword", {})),
        tts=TTSConfig(**raw.get("tts", {})),
        heartbeat=HeartbeatConfig(**raw.get("heartbeat", {})),
        brave=BraveConfig(**raw.get("brave", {})),
        bash=BashConfig(**raw.get("bash", {})),
        mcp_servers=raw.get("mcp_servers") or raw.get("mcpServers") or {},
    )
