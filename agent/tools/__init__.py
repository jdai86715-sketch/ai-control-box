from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    event: str
    data: dict[str, Any]
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "event": self.event, "data": self.data, "message": self.message}


from .device import get_temperature, set_fan, set_light
from .environment import get_system_time, get_weather


TOOL_DESCRIPTIONS = {
    "set_light": "Control a simulated room light and brightness.",
    "set_fan": "Control a simulated room fan speed.",
    "get_temperature": "Read a simulated room temperature.",
    "get_system_time": "Read the current local system date and time.",
    "get_weather": "Read the current weather for the configured location.",
    "list_tools": "List all available local tools.",
}


def list_tools() -> ToolResult:
    items = [{"name": name, "description": description} for name, description in TOOL_DESCRIPTIONS.items()]
    return ToolResult(True, "tools.list", {"tools": items}, "Available tools")


TOOLS: dict[str, Callable[..., ToolResult]] = {
    "set_light": set_light,
    "set_fan": set_fan,
    "get_temperature": get_temperature,
    "get_system_time": get_system_time,
    "get_weather": get_weather,
    "list_tools": list_tools,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "set_light", "description": "Turn on a simulated room light and optionally set brightness.", "parameters": {"type": "object", "properties": {"room": {"type": "string", "description": "Room name, such as bedroom or living room."}, "brightness": {"type": "integer", "minimum": 0, "maximum": 100}}, "required": ["room"]}},
    {"name": "set_fan", "description": "Turn on a simulated room fan and set its speed level.", "parameters": {"type": "object", "properties": {"room": {"type": "string", "description": "Room name, such as bedroom or living room."}, "level": {"type": "integer", "minimum": 1, "maximum": 3}}, "required": ["room"]}},
    {"name": "get_temperature", "description": "Read the simulated temperature of a room.", "parameters": {"type": "object", "properties": {"room": {"type": "string", "description": "Room name, such as bedroom or living room."}}, "required": ["room"]}},
    {"name": "get_system_time", "description": TOOL_DESCRIPTIONS["get_system_time"], "parameters": {"type": "object", "properties": {}}},
    {"name": "get_weather", "description": TOOL_DESCRIPTIONS["get_weather"], "parameters": {"type": "object", "properties": {}}},
    {"name": "list_tools", "description": TOOL_DESCRIPTIONS["list_tools"], "parameters": {"type": "object", "properties": {}}},
]

TOOL_INDEX_PATH = Path(__file__).with_name("tool_index.json")


def tool_schemas(names: list[str] | None = None) -> list[dict[str, Any]]:
    if names is None:
        return TOOL_SCHEMAS
    allowed = set(names)
    return [schema for schema in TOOL_SCHEMAS if schema["name"] in allowed]


def select_tools(text: str) -> list[str]:
    query = text.casefold()
    index = json.loads(TOOL_INDEX_PATH.read_text(encoding="utf-8"))
    return [
        name for name, entry in index.items()
        if name in TOOLS and any(str(word).casefold() in query for word in entry.get("keywords", []))
    ]


def execute(call: dict[str, Any]) -> dict[str, Any]:
    name = str(call.get("name", ""))
    handler = TOOLS.get(name)
    if handler is None:
        return ToolResult(False, "tool.error", {"name": name}, f"没有名为 {name} 的动作").as_dict()
    try:
        return handler(**dict(call.get("arguments") or {})).as_dict()
    except (TypeError, ValueError) as error:
        return ToolResult(False, "tool.error", {"name": name}, f"{name} 参数不正确：{error}").as_dict()
