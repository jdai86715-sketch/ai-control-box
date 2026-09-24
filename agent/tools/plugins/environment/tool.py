from datetime import datetime
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from agent.config import get_settings
from agent.tools.runtime import ToolResult


WEATHER_NAMES = {0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇", 51: "毛毛雨", 53: "毛毛雨", 55: "强毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "强阵雨", 82: "暴雨", 95: "雷暴"}
GEOCODING_GET_URL = "https://geocoding-api.open-meteo.com/v1/get"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = {
    "temperature": "temperature_2m",
    "feels_like": "apparent_temperature",
    "humidity": "relative_humidity_2m",
    "precipitation_probability": "precipitation_probability",
    "precipitation": "precipitation",
    "weather_code": "weather_code",
    "wind_speed": "wind_speed_10m",
    "cloud_cover": "cloud_cover",
    "visibility": "visibility",
    "uv_index": "uv_index",
}
DAILY_FIELDS = {
    "temperature": "temperature_2m_max,temperature_2m_min",
    "feels_like": "apparent_temperature_max,apparent_temperature_min",
    "precipitation_probability": "precipitation_probability_max",
    "precipitation": "precipitation_sum",
    "weather_code": "weather_code",
    "wind_speed": "wind_speed_10m_max",
    "uv_index": "uv_index_max",
}


def weather_agent_context() -> str:
    location = get_settings()["location"]
    return (
        f"Default weather location is {location['city']} ({location['latitude']}, {location['longitude']}). "
        "When the user does not name a location, call get_weather without location_id."
    )


def get_system_time() -> ToolResult:
    now = datetime.now().astimezone()
    return ToolResult(True, "time.read", {"datetime": now.isoformat(), "timezone": now.tzname()}, f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}")


def get_weather(
    location_id: int | None = None,
    view: str = "current",
    fields: list[str] | None = None,
    hours: int = 24,
    forecast_days: int = 3,
) -> ToolResult:
    location = _weather_location(location_id)
    if isinstance(location, ToolResult):
        return location
    if view not in {"current", "hourly", "daily"}:
        raise ValueError("view must be current, hourly, or daily")
    try:
        if view == "current":
            return _current_weather(location)
        if view == "hourly":
            return _hourly_weather(location, fields, hours)
        return _daily_weather(location, fields, forecast_days)
    except Exception as error:
        return ToolResult(False, "weather.error", {"city": location["city"]}, f"{location['city']}天气获取失败：{error}")


def _weather_location(location_id: int | None) -> dict | ToolResult:
    if location_id is None:
        location = get_settings()["location"]
        return {"city": location["city"], "latitude": location["latitude"], "longitude": location["longitude"], "timezone": "auto"}
    try:
        with urlopen(f"{GEOCODING_GET_URL}?{urlencode({'id': int(location_id), 'language': 'zh'})}", timeout=8) as response:
            location = json.load(response)
    except Exception as error:
        return ToolResult(False, "location.error", {"location_id": location_id}, f"地点读取失败：{error}")
    if not isinstance(location, dict) or "latitude" not in location or "longitude" not in location:
        return ToolResult(False, "location.not_found", {"location_id": location_id}, f"未找到地点 ID：{location_id}")
    return {"city": location.get("name", str(location_id)), "latitude": location["latitude"], "longitude": location["longitude"], "timezone": location.get("timezone", "auto"), "location_id": int(location_id)}


def _forecast(location: dict, **parameters: object) -> dict:
    query = {"latitude": location["latitude"], "longitude": location["longitude"], "timezone": location["timezone"], **parameters}
    with urlopen(f"{FORECAST_URL}?{urlencode(query)}", timeout=8) as response:
        return json.load(response)


def _current_weather(location: dict) -> ToolResult:
    current = _forecast(location, current="temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,precipitation,wind_speed_10m,wind_direction_10m")["current"]
    condition = WEATHER_NAMES.get(current["weather_code"], f"天气代码 {current['weather_code']}")
    data = {"city": location["city"], "temperature": current["temperature_2m"], "feels_like": current["apparent_temperature"], "humidity": current["relative_humidity_2m"], "weather_code": current["weather_code"], "condition": condition, "precipitation": current["precipitation"], "wind_speed": current["wind_speed_10m"], "wind_direction": current["wind_direction_10m"]}
    return ToolResult(True, "weather.current", data, f"{location['city']}当前{condition}，{current['temperature_2m']}°C，体感{current['apparent_temperature']}°C，湿度{current['relative_humidity_2m']}%，风速{current['wind_speed_10m']} km/h")


def _hourly_weather(location: dict, fields: list[str] | None, hours: int) -> ToolResult:
    selected = _selected_fields(fields, HOURLY_FIELDS, ["temperature"])
    if not 1 <= int(hours) <= 48:
        raise ValueError("hours must be between 1 and 48")
    raw = _forecast(location, hourly=",".join(HOURLY_FIELDS[field] for field in selected), forecast_hours=int(hours))["hourly"]
    rows = [{"time": raw["time"][index], **{field: raw[HOURLY_FIELDS[field]][index] for field in selected}} for index in range(min(int(hours), len(raw["time"])))]
    return ToolResult(True, "weather.hourly", {"city": location["city"], "fields": selected, "hours": len(rows), "rows": rows}, f"{location['city']}未来{len(rows)}小时天气：" + "；".join(_hourly_label(row, selected) for row in rows))


def _daily_weather(location: dict, fields: list[str] | None, forecast_days: int) -> ToolResult:
    selected = _selected_fields(fields, DAILY_FIELDS, ["temperature", "weather_code", "precipitation_probability"])
    if not 1 <= int(forecast_days) <= 7:
        raise ValueError("forecast_days must be between 1 and 7")
    requested = sorted({item for field in selected for item in DAILY_FIELDS[field].split(",")})
    raw = _forecast(location, daily=",".join(requested), forecast_days=int(forecast_days))["daily"]
    rows = [{"date": raw["time"][index], **{field: _daily_value(raw, field, index) for field in selected}} for index in range(min(int(forecast_days), len(raw["time"])))]
    return ToolResult(True, "weather.daily", {"city": location["city"], "fields": selected, "days": len(rows), "rows": rows}, f"{location['city']}未来{len(rows)}天天气：" + "；".join(_daily_label(row) for row in rows))


def _selected_fields(fields: list[str] | None, supported: dict[str, str], defaults: list[str]) -> list[str]:
    if fields is None:
        return defaults
    if not isinstance(fields, list) or not fields:
        raise ValueError("fields must be a non-empty list")
    selected = list(dict.fromkeys(str(field) for field in fields))
    unknown = [field for field in selected if field not in supported]
    if unknown:
        raise ValueError(f"unsupported fields: {', '.join(unknown)}")
    return selected


def _hourly_label(row: dict, fields: list[str]) -> str:
    values = ", ".join(f"{field}={row[field]}" for field in fields)
    return f"{row['time']} {values}"


def _daily_value(raw: dict, field: str, index: int):
    names = DAILY_FIELDS[field].split(",")
    values = [raw[name][index] for name in names]
    if field == "weather_code":
        return {"code": values[0], "condition": WEATHER_NAMES.get(values[0], f"天气代码 {values[0]}")}
    return values[0] if len(values) == 1 else {"max": values[0], "min": values[1]}


def _daily_label(row: dict) -> str:
    parts = []
    for key, value in row.items():
        if key == "date":
            continue
        parts.append(f"{key}={value}")
    return f"{row['date']} {', '.join(parts)}"
