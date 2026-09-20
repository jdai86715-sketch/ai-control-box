"""Reads and writes environment settings that belong outside the agent code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SETTINGS_PATH = Path(__file__).parent.parent / "settings" / "environment.json"


def get_settings() -> dict[str, Any]:
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    location = data.get("location") or {}
    city = str(location.get("city", "")).strip()
    latitude = float(location.get("latitude"))
    longitude = float(location.get("longitude"))
    if not city:
        raise ValueError("请填写城市。")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("经纬度范围不正确。")
    settings = {"location": {"city": city, "latitude": latitude, "longitude": longitude}}
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return settings
