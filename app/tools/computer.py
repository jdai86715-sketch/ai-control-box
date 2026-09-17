from __future__ import annotations

from datetime import datetime
from pathlib import Path
from subprocess import Popen
from typing import Any

from app.config import settings
from app.models import RiskLevel
from app.tools.registry import Tool, registry


def get_time(_: dict[str, Any]) -> dict[str, Any]:
    return {"本机时间": datetime.now().astimezone().isoformat()}


def open_app(arguments: dict[str, Any]) -> dict[str, Any]:
    app_name = str(arguments.get("app_name", "")).strip()
    command = settings.app_map.get(app_name)
    if not command:
        return {"成功": False, "说明": f"应用未获授权：{app_name}", "已授权应用": list(settings.app_map)}
    Popen([command])
    return {"成功": True, "说明": f"已启动：{app_name}"}


def list_files(arguments: dict[str, Any]) -> dict[str, Any]:
    requested = Path(str(arguments.get("directory", ""))).expanduser().resolve()
    if not any(requested == safe or safe in requested.parents for safe in settings.safe_paths):
        return {"成功": False, "说明": "该目录不在安全浏览范围内。"}
    if not requested.is_dir():
        return {"成功": False, "说明": "目录不存在或不可访问。"}
    files = [{"名称": item.name, "类型": "文件夹" if item.is_dir() else "文件"} for item in list(requested.iterdir())[:100]]
    return {"成功": True, "目录": str(requested), "内容": files}


registry.register(Tool("get_time", "获取本机当前时间。", RiskLevel.LOW, get_time))
registry.register(Tool("open_app", "启动已授权的 Windows 应用。", RiskLevel.MEDIUM, open_app))
registry.register(Tool("list_files", "浏览安全目录内的文件。", RiskLevel.LOW, list_files))