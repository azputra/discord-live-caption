from __future__ import annotations

from app.models import AudioDevice

_LOOPBACK_TOKENS = ("blackhole", "soundflower", "loopback", "stereo mix")


def is_virtual_loopback_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _LOOPBACK_TOKENS)


def is_blackhole_name(name: str) -> bool:
    return "blackhole" in name.lower()


def find_blackhole(devices: list[AudioDevice]) -> AudioDevice | None:
    matches = [device for device in devices if is_blackhole_name(device.name)]
    for device in matches:
        if "2ch" in device.name.lower():
            return device
    return matches[0] if matches else None


def blackhole_present(devices: list[AudioDevice]) -> bool:
    return find_blackhole(devices) is not None


def split_macos_devices(
    inputs: list[AudioDevice],
) -> tuple[list[AudioDevice], list[AudioDevice]]:
    system = [device for device in inputs if is_virtual_loopback_name(device.name)]
    mics = [device for device in inputs if not is_virtual_loopback_name(device.name)]
    return system, mics


def prefer_host_api(devices: list[AudioDevice], host_name: str) -> list[AudioDevice]:
    matched = [device for device in devices if host_name.lower() in device.host_api.lower()]
    return matched or list(devices)


def exclude_loopback_mics(devices: list[AudioDevice]) -> list[AudioDevice]:
    return [device for device in devices if not is_virtual_loopback_name(device.name)]


def match_loopback(
    devices: list[AudioDevice],
    output_name: str | None,
) -> AudioDevice | None:
    loopbacks = [device for device in devices if device.kind == "loopback" or is_virtual_loopback_name(device.name)]
    if not loopbacks:
        return None
    if output_name:
        needle = output_name.lower()
        for device in loopbacks:
            if needle in device.name.lower() or device.name.lower() in needle:
                return device
    for device in loopbacks:
        if device.is_default:
            return device
    return loopbacks[0]


def recommended_system_device(
    devices: list[AudioDevice],
    platform_name: str,
    output_name: str | None = None,
) -> AudioDevice | None:
    if platform_name == "macos":
        blackhole = find_blackhole(devices)
        if blackhole is not None:
            return blackhole
        return devices[0] if devices else None
    return match_loopback(devices, output_name)


def recommended_mic(devices: list[AudioDevice]) -> AudioDevice | None:
    for device in devices:
        if device.is_default:
            return device
    return devices[0] if devices else None
