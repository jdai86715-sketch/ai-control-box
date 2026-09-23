import json
from urllib.parse import urlencode
from urllib.request import urlopen

from agent.tools.runtime import ToolResult


GEOCODING_SEARCH_URL = "https://geocoding-api.open-meteo.com/v1/search"


def search_location(query: str) -> ToolResult:
    query = query.strip()
    if len(query) < 2:
        raise ValueError("query must contain at least two characters")
    try:
        with urlopen(f"{GEOCODING_SEARCH_URL}?{urlencode({'name': query, 'count': 1, 'language': 'zh'})}", timeout=8) as response:
            location = (json.load(response).get("results") or [None])[0]
    except Exception as error:
        return ToolResult(False, "location.error", {"query": query}, f"地点搜索失败：{error}")
    if not isinstance(location, dict):
        return ToolResult(False, "location.not_found", {"query": query}, f"未找到地点：{query}")
    location_id = int(location["id"])
    data = {
        "location_id": location_id,
        "name": location.get("name", query),
        "country": location.get("country", ""),
        "admin1": location.get("admin1", ""),
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "timezone": location.get("timezone", ""),
        "next_tool_call": {"name": "get_weather", "arguments": {"location_id": location_id}},
        "agent_continuation": {"tool": "get_weather", "arguments": {"location_id": location_id}},
    }
    label = "，".join(part for part in [data["name"], data["admin1"], data["country"]] if part)
    return ToolResult(True, "location.found", data, f"已定位：{label}")
