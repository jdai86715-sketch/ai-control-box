from __future__ import annotations

from dataclasses import dataclass
import re
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

TOOL_TRIGGERS = {
    "set_light": [r"\b(light|lamp)\b"],
    "set_fan": [r"\bfan\b"],
    "get_temperature": [r"\b(temp|temperature)\b"],
    "get_system_time": [r"\b(time|clock|date)\b"],
    "get_weather": [r"\b(weather|forecast|rain)\b"],
    "list_tools": [r"\btools?\b"],
}

for _schema in TOOL_SCHEMAS:
    _schema["triggers"] = TOOL_TRIGGERS[_schema["name"]]

PARAMETER_ALIASES = {
    "set_fan": {"level": ("level", "speed")},
}

def tool_schemas(names: list[str] | None = None) -> list[dict[str, Any]]:
    if names is None:
        return TOOL_SCHEMAS
    allowed = set(names)
    return [schema for schema in TOOL_SCHEMAS if schema["name"] in allowed]


def execute(call: dict[str, Any]) -> dict[str, Any]:
    name = str(call.get("name", ""))
    handler = TOOLS.get(name)
    if handler is None:
        return ToolResult(False, "tool.error", {"name": name}, f"没有名为 {name} 的动作").as_dict()
    try:
        return handler(**dict(call.get("arguments") or {})).as_dict()
    except (TypeError, ValueError) as error:
        return ToolResult(False, "tool.error", {"name": name}, f"{name} 参数不正确：{error}").as_dict()


def constraint_error(response: dict[str, Any]) -> dict[str, Any] | None:
    """Turn Needle's range-constrained truncation into a specific user-facing error."""
    if response.get("error_code") != "truncated":
        return None
    reasoning = str(response.get("reasoning", ""))
    for schema in TOOL_SCHEMAS:
        for parameter, definition in schema["parameters"].get("properties", {}).items():
            minimum = definition.get("minimum")
            maximum = definition.get("maximum")
            if minimum is None and maximum is None:
                continue
            match = re.search(rf"\b{re.escape(parameter)}\s*(?:=|:)?\s*(-?\d+(?:\.\d+)?)", reasoning, re.I)
            if match is None:
                continue
            value = float(match.group(1))
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                limits = f"between {minimum} and {maximum}" if minimum is not None and maximum is not None else f"at least {minimum}" if minimum is not None else f"at most {maximum}"
                return ToolResult(False, "tool.error", {"name": schema["name"], "parameter": parameter, "value": value}, f"{schema['name']}: {parameter} must be {limits}.").as_dict()
    return None


def input_constraint_error(call: dict[str, Any], text: str) -> dict[str, Any] | None:
    """Reject an out-of-range number in the request before model defaults can hide it."""
    name = str(call.get("name", ""))
    schema = next((item for item in TOOL_SCHEMAS if item["name"] == name), None)
    if schema is None:
        return None
    aliases_by_parameter = PARAMETER_ALIASES.get(name, {})
    for parameter, definition in schema["parameters"].get("properties", {}).items():
        minimum = definition.get("minimum")
        maximum = definition.get("maximum")
        if minimum is None and maximum is None:
            continue
        aliases = aliases_by_parameter.get(parameter, (parameter,))
        terms = "|".join(re.escape(alias) for alias in aliases)
        match = re.search(rf"\b(?:{terms})\s*(?:=|:)?\s*(-?\d+(?:\.\d+)?)", text, re.I)
        if match is None:
            continue
        value = float(match.group(1))
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            limits = f"between {minimum} and {maximum}" if minimum is not None and maximum is not None else f"at least {minimum}" if minimum is not None else f"at most {maximum}"
            return ToolResult(False, "tool.error", {"name": name, "parameter": parameter, "value": value}, f"{name}: {parameter} must be {limits}.").as_dict()
    return None
