from __future__ import annotations

from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from ..config import get_settings
from . import ToolResult


WEATHER_NAMES = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    95: "雷暴",
}


def get_system_time() -> ToolResult:
    now = datetime.now().astimezone()
    value = now.strftime("%Y-%m-%d %H:%M")
    return ToolResult(True, "time.read", {"datetime": now.isoformat(), "timezone": now.tzname()}, f"当前时间：{value}")


def get_weather() -> ToolResult:
    location = get_settings()["location"]
    query = urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": "temperature_2m,weather_code",
    })
    try:
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=8) as response:
            current = json.load(response)["current"]
    except Exception as error:
        return ToolResult(False, "weather.error", {"city": location["city"]}, f"{location['city']}天气获取失败：{error}")
    temperature = current["temperature_2m"]
    code = current["weather_code"]
    condition = WEATHER_NAMES.get(code, f"天气代码 {code}")
    return ToolResult(
        True,
        "weather.read",
        {"city": location["city"], "temperature": temperature, "weather_code": code, "condition": condition},
        f"{location['city']}当前{condition}，{temperature}°C",
    )
