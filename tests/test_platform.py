import sys

import pytest

from app.audio.capture import UnsupportedPlatform, backend_for_platform, create_capture
from app.audio.capture_windows import WindowsAudioCapture
from app.audio.devices import (
    find_blackhole,
    match_loopback,
    recommended_system_device,
    split_macos_devices,
)
from app.models import AudioDevice


def test_backend_name_for_each_os():
    assert backend_for_platform("win32") == "windows"
    assert backend_for_platform("darwin") == "macos"
    with pytest.raises(UnsupportedPlatform):
        backend_for_platform("linux")


def test_factory_uses_explicit_platform():
    assert create_capture("win32").platform_name == "windows"
    assert create_capture("darwin").platform_name == "macos"
    with pytest.raises(UnsupportedPlatform):
        create_capture("linux")


def test_factory_follows_sys_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert create_capture().platform_name == "windows"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert create_capture().platform_name == "macos"


def test_windows_module_imports_without_pyaudiowpatch():
    capture = WindowsAudioCapture()
    assert capture.platform_name == "windows"


def test_blackhole_detection_prefers_2ch():
    devices = [
        AudioDevice("1", "BlackHole 16ch", 16, 48000, "input"),
        AudioDevice("2", "BlackHole 2ch", 2, 48000, "input"),
        AudioDevice("3", "MacBook Microphone", 1, 48000, "input"),
    ]
    assert find_blackhole(devices).id == "2"
    system, mics = split_macos_devices(devices)
    assert [device.id for device in system] == ["1", "2"]
    assert [device.id for device in mics] == ["3"]
    assert recommended_system_device(system, "macos").id == "2"


def test_windows_loopback_matches_output_name():
    devices = [
        AudioDevice("4", "Speakers (Realtek) [Loopback]", 2, 48000, "loopback"),
        AudioDevice("5", "Headphones [Loopback]", 2, 48000, "loopback"),
    ]
    assert match_loopback(devices, "Headphones").id == "5"
    assert recommended_system_device(devices, "windows", "Speakers (Realtek)").id == "4"


@pytest.mark.skipif(sys.platform != "darwin", reason="CoreAudio device listing is macOS-only")
def test_macos_device_listing_does_not_crash():
    pytest.importorskip("sounddevice")
    from app.audio.capture_macos import MacAudioCapture

    capture = MacAudioCapture()
    system = capture.list_system_devices()
    mics = capture.list_mic_devices()
    assert isinstance(system, list)
    assert isinstance(mics, list)


def test_missing_blackhole():
    devices = [AudioDevice("1", "MacBook Microphone", 1, 48000, "input")]
    assert find_blackhole(devices) is None
    system, _mics = split_macos_devices(devices)
    assert system == []
