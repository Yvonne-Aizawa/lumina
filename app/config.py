"""Configuration loading and path constants."""

import json
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
ASSETS_DIR = PROJECT_DIR / "assets"
ANIMS_DIR = ASSETS_DIR / "anims"
MODELS_DIR = ASSETS_DIR / "models"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
CONFIG_PATH = PROJECT_DIR / "config.json"
STATE_DIR = PROJECT_DIR / "state"
VRM_MODEL = "avatar.vrm"


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
    auto_start: bool = False


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
class AuthConfig:
    enabled: bool = False
    api_key: str = ""


@dataclass
class BashConfig:
    enabled: bool = False


@dataclass
class EmotionConfig:
    enabled: bool = False


@dataclass
class WebSearchConfig:
    enabled: bool = False
    brave: dict = field(default_factory=dict)

    @property
    def brave_api_key(self) -> str | None:
        if not self.enabled:
            return None
        brave = self.brave
        if not brave.get("enabled", False):
            return None
        return brave.get("api_key")


@dataclass
class VectorSearchConfig:
    enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"
    collection: str = "memories"


@dataclass
class BuiltinToolsConfig:
    animation: bool = True
    memory: bool = True
    memory_readonly: bool = False
    state: bool = True
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    vector_search: VectorSearchConfig = field(default_factory=VectorSearchConfig)
    bash: bool = True
    mcp_servers: bool = False
    mcp_servers_allow_network: bool = False


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    wakeword: WakeWordConfig = field(default_factory=WakeWordConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    bash: BashConfig = field(default_factory=BashConfig)
    builtin_tools: BuiltinToolsConfig = field(default_factory=BuiltinToolsConfig)
    emotion: EmotionConfig = field(default_factory=EmotionConfig)
    mcp_servers: dict[str, dict] = field(default_factory=dict)
    background: str | None = None


def _parse_builtin_tools(raw: dict) -> BuiltinToolsConfig:
    """Parse builtin_tools config, handling nested web_search object."""
    kw = {}
    for key in (
        "animation",
        "memory",
        "memory_readonly",
        "state",
        "bash",
        "mcp_servers",
        "mcp_servers_allow_network",
    ):
        if key in raw:
            kw[key] = raw[key]
    ws = raw.get("web_search", {})
    if isinstance(ws, bool):
        # Backwards compat: bare boolean
        kw["web_search"] = WebSearchConfig(enabled=ws)
    elif isinstance(ws, dict):
        kw["web_search"] = WebSearchConfig(
            enabled=ws.get("enabled", False),
            brave=ws.get("brave", {}),
        )
    vs = raw.get("vector_search", {})
    if isinstance(vs, dict) and vs:
        kw["vector_search"] = VectorSearchConfig(**vs)
    return BuiltinToolsConfig(**kw)


def load_config() -> Config:
    global STATE_DIR, ASSETS_DIR, ANIMS_DIR, MODELS_DIR, BACKGROUNDS_DIR, VRM_MODEL
    if not CONFIG_PATH.exists():
        return Config()
    raw = json.loads(CONFIG_PATH.read_text())
    if "state_dir" in raw:
        STATE_DIR = Path(raw["state_dir"]).resolve()
    if "assets_dir" in raw:
        ASSETS_DIR = Path(raw["assets_dir"]).resolve()
        ANIMS_DIR = ASSETS_DIR / "anims"
        MODELS_DIR = ASSETS_DIR / "models"
        BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"
    if "vrm_model" in raw:
        VRM_MODEL = raw["vrm_model"]
    return Config(
        llm=LLMConfig(**raw.get("llm", {})),
        stt=STTConfig(**raw.get("stt", {})),
        wakeword=WakeWordConfig(**raw.get("wakeword", {})),
        tts=TTSConfig(**raw.get("tts", {})),
        heartbeat=HeartbeatConfig(**raw.get("heartbeat", {})),
        auth=AuthConfig(**raw.get("auth", {})),
        bash=BashConfig(**raw.get("bash", {})),
        builtin_tools=_parse_builtin_tools(raw.get("builtin_tools", {})),
        emotion=EmotionConfig(**raw.get("emotion", {})),
        mcp_servers=raw.get("mcp_servers") or raw.get("mcpServers") or {},
        background=raw.get("background"),
    )
