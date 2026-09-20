from __future__ import annotations

from . import ToolResult


ROOM_NAMES = {
    "bedroom": "卧室",
    "living room": "客厅",
    "kitchen": "厨房",
}


def room_label(room: str) -> str:
    return ROOM_NAMES.get(room.lower(), room)


def set_light(room: str, brightness: int = 100) -> ToolResult:
    label = room_label(room)
    brightness = max(0, min(100, int(brightness)))
    return ToolResult(True, "light.set", {"room": label, "brightness": brightness}, f"{label}灯已打开，亮度 {brightness}%")


def set_fan(room: str, level: int = 1) -> ToolResult:
    label = room_label(room)
    level = max(1, min(3, int(level)))
    return ToolResult(True, "fan.set", {"room": label, "level": level}, f"{label}风扇已打开，当前 {level} 档")


def get_temperature(room: str) -> ToolResult:
    label = room_label(room)
    temperature = 24
    return ToolResult(True, "temperature.read", {"room": label, "temperature": temperature}, f"{label}当前温度 {temperature}°C")
