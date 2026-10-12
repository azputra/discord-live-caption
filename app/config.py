from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import yaml
from dotenv import load_dotenv


def _take(cls, raw: dict | None):
    payload = raw or {}
    defaults = cls()
    kwargs = {}
    for item in fields(cls):
        if item.name in payload and payload[item.name] is not None:
            kwargs[item.name] = payload[item.name]
        else:
            kwargs[item.name] = getattr(defaults, item.name)
    return cls(**kwargs)


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    block_ms: int = 30
    system_device: str | None = None
    mic_device: str | None = None
    save_audio: bool = False


@dataclass
class VadConfig:
    provider: str = "silero"
    threshold: float = 0.5
    energy_threshold: float = 0.02
    min_speech_ms: int = 250
    min_silence_ms: int = 500
    speech_pad_ms: int = 200
    max_segment_s: float = 20
    partial_interval_s: float = 2.5


@dataclass
class SttConfig:
    provider: str = "faster-whisper"
    model_size: str = "small"
    language: str = "auto"
    device: str = "auto"
    compute_type: str = "auto"
    no_speech_threshold: float = 0.6


@dataclass
class TranslationConfig:
    provider: str = "llm"
    mode: str = "swap"
    target_language: str = "en"
    llm_vendor: str = "openai"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    context_segments: int = 5
    display: str = "both"


@dataclass
class UiConfig:
    language: str = "en"
    theme: str = "system"
    overlay_opacity: float = 0.88
    overlay_font_size: int = 18
    overlay_lines: int = 6
    summary_language: str = "en"


@dataclass
class LogConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    logging: LogConfig = field(default_factory=LogConfig)

    def __post_init__(self) -> None:
        self.config_path = Path("config.yaml")
        self.env_path = Path(".env")

    @classmethod
    def from_dict(cls, data: dict | None) -> AppConfig:
        payload = data or {}
        return cls(
            audio=_take(AudioConfig, payload.get("audio")),
            vad=_take(VadConfig, payload.get("vad")),
            stt=_take(SttConfig, payload.get("stt")),
            translation=_take(TranslationConfig, payload.get("translation")),
            ui=_take(UiConfig, payload.get("ui")),
            logging=_take(LogConfig, payload.get("logging")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discover_config_path() -> Path:
    cwd_path = Path.cwd() / "config.yaml"
    packaged = package_root() / "config.yaml"
    if cwd_path.is_file():
        return cwd_path
    if packaged.is_file():
        return packaged
    return cwd_path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = Path(path) if path is not None else discover_config_path()
    data: dict = {}
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        data = loaded or {}
    env_path = config_path.parent / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    config = AppConfig.from_dict(data)
    config.config_path = config_path
    config.env_path = env_path
    _coerce(config)
    return config


def _coerce(config: AppConfig) -> None:
    if config.audio.system_device is not None:
        config.audio.system_device = str(config.audio.system_device)
    if config.audio.mic_device is not None:
        config.audio.mic_device = str(config.audio.mic_device)
    config.stt.model_size = str(config.stt.model_size)
    config.stt.language = str(config.stt.language)
    config.translation.mode = str(config.translation.mode)
    config.translation.target_language = str(config.translation.target_language)
    config.ui.language = str(config.ui.language)
    config.ui.summary_language = str(config.ui.summary_language)
    config.vad.provider = str(config.vad.provider)
    config.stt.provider = str(config.stt.provider)
    config.translation.provider = str(config.translation.provider)


def save_config(config: AppConfig) -> None:
    config.config_path.parent.mkdir(parents=True, exist_ok=True)
    dumped = yaml.safe_dump(
        config.to_dict(),
        sort_keys=False,
        allow_unicode=True,
    )
    config.config_path.write_text(dumped, encoding="utf-8")


def api_key_status() -> dict[str, bool]:
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
    }


def write_env_key(env_path: Path, name: str, value: str) -> None:
    cleaned = value.strip()
    env_path = Path(env_path)
    existing: list[str] = []
    if env_path.is_file():
        existing = env_path.read_text(encoding="utf-8").splitlines()
    prefix = f"{name}="
    export_prefix = f"export {name}="
    replaced = False
    updated: list[str] = []
    for line in existing:
        stripped = line.strip()
        if stripped.startswith(prefix) or stripped.startswith(export_prefix):
            updated.append(f"{name}={cleaned}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        if updated and updated[-1] != "":
            updated.append(f"{name}={cleaned}")
        else:
            updated.append(f"{name}={cleaned}")
    text = "\n".join(updated).rstrip() + "\n"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(text, encoding="utf-8")
    os.environ[name] = cleaned
