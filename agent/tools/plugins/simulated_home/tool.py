from agent.tools.runtime import ToolResult


ROOM_NAMES = {"bedroom": "卧室", "living room": "客厅", "kitchen": "厨房"}
ROOM_ALIASES = {"卧室": "bedroom", "客厅": "living room", "厨房": "kitchen"}


def room_label(room: str) -> str:
    key = ROOM_ALIASES.get(str(room).strip(), str(room).strip().lower())
    if key not in ROOM_NAMES:
        raise ValueError("room must be one of bedroom, living room, kitchen")
    return ROOM_NAMES[key]


def set_light(room: str, brightness: int = 100) -> ToolResult:
    label = room_label(room)
    brightness = max(0, min(100, int(brightness)))
    message = f"{label}灯已关闭" if brightness == 0 else f"{label}灯已打开，亮度 {brightness}%"
    return ToolResult(True, "light.set", {"room": label, "brightness": brightness}, message)


def set_fan(room: str, level: int = 1) -> ToolResult:
    label = room_label(room)
    level = max(0, min(3, int(level)))
    message = f"{label}风扇已关闭" if level == 0 else f"{label}风扇已打开，当前 {level} 档"
    return ToolResult(True, "fan.set", {"room": label, "level": level}, message)


def get_temperature(room: str) -> ToolResult:
    label = room_label(room)
    return ToolResult(True, "temperature.read", {"room": label, "temperature": 24}, f"{label}当前温度 24°C")
