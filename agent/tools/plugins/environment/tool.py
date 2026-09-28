from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from agent.config import get_device_locations, get_settings
from agent.tools.runtime import ToolResult


WEATHER_NAMES = {0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇", 51: "毛毛雨", 53: "毛毛雨", 55: "强毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "强阵雨", 82: "暴雨", 95: "雷暴"}


def get_system_time() -> ToolResult:
    now = datetime.now().astimezone()
    return ToolResult(True, "time.read", {"datetime": now.isoformat(), "timezone": now.tzname()}, f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}")


def get_device_location(device: str) -> ToolResult:
    requested = str(device).strip().lower()
    for item in get_device_locations().get("devices", []):
        aliases = [item["id"], item["name"], *item.get("aliases", [])]
        if requested in {str(alias).strip().lower() for alias in aliases}:
            data = {key: item[key] for key in ("id", "name", "city", "latitude", "longitude")}
            return ToolResult(True, "device.location.read", data, f"{data['name']}当前模拟位置：{data['city']}")
    return ToolResult(False, "device.not_found", {"device": device}, f"未找到模拟设备：{device}")


def resolve_city(city: str) -> ToolResult:
    name = str(city).strip()
    if not name:
        raise ValueError("city is required")
    query = urlencode({"name": name, "count": 1, "language": "zh", "format": "json"})
    try:
        with urlopen(f"https://geocoding-api.open-meteo.com/v1/search?{query}", timeout=8) as response:
            results = json.load(response).get("results") or []
    except Exception as error:
        return ToolResult(False, "city.error", {"city": name}, f"{name}城市查询失败：{error}")
    if not results:
        return ToolResult(False, "city.not_found", {"city": name}, f"未找到城市：{name}")
    match = results[0]
    data = {"city": match["name"], "location_id": match.get("id"), "latitude": match["latitude"], "longitude": match["longitude"], "country": match.get("country")}
    return ToolResult(True, "city.resolve", data, f"已找到{data['city']}，城市 ID {data['location_id']}")


def get_weather(city: str | None = None, latitude: float | None = None, longitude: float | None = None) -> ToolResult:
    location = get_settings()["location"] if latitude is None or longitude is None else {"city": city or "指定城市", "latitude": float(latitude), "longitude": float(longitude)}
    query = urlencode({"latitude": location["latitude"], "longitude": location["longitude"], "current": "temperature_2m,weather_code"})
    try:
        with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=8) as response:
            current = json.load(response)["current"]
    except Exception as error:
        return ToolResult(False, "weather.error", {"city": location["city"]}, f"{location['city']}天气获取失败：{error}")
    condition = WEATHER_NAMES.get(current["weather_code"], f"天气代码 {current['weather_code']}")
    return ToolResult(True, "weather.read", {"city": location["city"], "temperature": current["temperature_2m"], "weather_code": current["weather_code"], "condition": condition}, f"{location['city']}当前{condition}，{current['temperature_2m']}°C")
