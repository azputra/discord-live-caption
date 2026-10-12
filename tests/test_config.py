from pathlib import Path

from app.config import AppConfig, load_config, save_config, write_env_key
from app.stt.faster_whisper_provider import resolve_whisper_device


def test_shipped_config_loads():
    path = Path(__file__).resolve().parents[1] / "config.yaml"
    config = load_config(path)
    assert config.stt.provider == "faster-whisper"
    assert config.stt.model_size == "small"
    assert config.translation.mode == "swap"
    assert config.translation.provider == "llm"
    assert config.audio.save_audio is False
    assert config.vad.provider == "silero"


def test_partial_config_keeps_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("stt:\n  provider: mock\n", encoding="utf-8")
    config = load_config(path)
    assert config.stt.provider == "mock"
    assert config.stt.model_size == "small"
    assert config.translation.mode == "swap"
    config.translation.mode = "fixed"
    save_config(config)
    assert load_config(path).translation.mode == "fixed"


def test_blank_env_update_replaces_one_key(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=old\nANTHROPIC_API_KEY=keep\n", encoding="utf-8")
    write_env_key(env_path, "OPENAI_API_KEY", "new-key")
    text = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=new-key" in text
    assert "ANTHROPIC_API_KEY=keep" in text
    assert text.count("OPENAI_API_KEY=") == 1
    monkeypatch.setenv("OPENAI_API_KEY", "")
    write_env_key(env_path, "OPENAI_API_KEY", "fresh")
    assert "OPENAI_API_KEY=fresh" in env_path.read_text(encoding="utf-8")


def test_appconfig_roundtrip_ignores_paths():
    config = AppConfig.from_dict({"ui": {"language": "id"}})
    assert config.ui.language == "id"
    assert "config_path" not in config.to_dict()


def test_whisper_device_selection(monkeypatch):
    monkeypatch.setattr(
        "app.stt.faster_whisper_provider.cuda_available",
        lambda: False,
    )
    assert resolve_whisper_device("auto", "auto") == ("cpu", "int8")
    assert resolve_whisper_device("cuda", "auto") == ("cpu", "int8")
    monkeypatch.setattr(
        "app.stt.faster_whisper_provider.cuda_available",
        lambda: True,
    )
    assert resolve_whisper_device("auto", "auto") == ("cuda", "float16")
    assert resolve_whisper_device("cpu", "auto") == ("cpu", "int8")


def test_requirements_use_environment_markers():
    text = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert 'sys_platform == "win32"' in text
    assert 'sys_platform == "darwin"' in text
    assert "pyaudiowpatch" in text
    assert "pyobjc-framework-Cocoa" in text
