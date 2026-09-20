from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path, PurePosixPath
import re
from threading import RLock, Thread
from time import sleep
from typing import Any, Callable


PLUGINS = Path(__file__).with_name("plugins")


@dataclass
class ToolResult:
    ok: bool
    event: str
    data: dict[str, Any]
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "event": self.event, "data": self.data, "message": self.message}


@dataclass
class RegisteredTool:
    schema: dict[str, Any]
    meta: dict[str, Any]
    handler: Callable[..., ToolResult]


class ToolRegistry:
    def __init__(self, plugins_path: Path = PLUGINS) -> None:
        self.plugins_path = plugins_path
        self._signature = ""
        self._tools: dict[str, RegisteredTool] = {}
        self._errors: list[dict[str, str]] = []
        self._lock = RLock()
        self.version = ""
        self.refresh(force=True)
        self._watcher = Thread(target=self._watch, name="tool-plugin-watcher", daemon=True)
        self._watcher.start()

    def _watch(self) -> None:
        while True:
            sleep(1)
            self.refresh()

    def refresh(self, force: bool = False) -> bool:
        with self._lock:
            signature = self._filesystem_signature()
            if not force and signature == self._signature:
                return False
            tools: dict[str, RegisteredTool] = {}
            errors: list[dict[str, str]] = []
            self.plugins_path.mkdir(parents=True, exist_ok=True)
            for directory in sorted(path for path in self.plugins_path.iterdir() if path.is_dir() and not path.name.startswith(".")):
                if not any(path.name != "__pycache__" for path in directory.iterdir()):
                    continue
                try:
                    self._load_plugin(directory, tools)
                except Exception as error:
                    errors.append({"plugin": directory.name, "message": str(error)})
            self._tools = tools
            self._errors = errors
            self._signature = signature
            self.version = signature
            return True

    def _filesystem_signature(self) -> str:
        self.plugins_path.mkdir(parents=True, exist_ok=True)
        digest = sha256()
        for path in sorted(item for item in self.plugins_path.rglob("*") if item.is_file()):
            stat = path.stat()
            digest.update(str(path.relative_to(self.plugins_path)).replace("\\", "/").encode())
            digest.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode())
        return digest.hexdigest()

    def _load_plugin(self, directory: Path, tools: dict[str, RegisteredTool]) -> None:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        plugin_id = self._required_text(manifest, "id")
        if plugin_id != directory.name:
            raise ValueError("manifest id must match its folder name")
        entry = directory / str(manifest.get("entry", "tool.py"))
        if not entry.is_file():
            raise ValueError("entry file is missing")
        module_name = f"control_box_plugin_{plugin_id}_{self._signature[:12]}"
        spec = spec_from_file_location(module_name, entry)
        if spec is None or spec.loader is None:
            raise ValueError("entry file cannot be loaded")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        for item in manifest.get("tools", []):
            name = self._required_text(item, "name")
            function_name = self._required_text(item, "function")
            if name in tools:
                raise ValueError(f"duplicate tool name: {name}")
            handler = getattr(module, function_name, None)
            if not callable(handler):
                raise ValueError(f"function is missing: {function_name}")
            parameters = item.get("parameters", {"type": "object", "properties": {}})
            if not isinstance(parameters, dict):
                raise ValueError(f"parameters must be an object: {name}")
            schema = {"name": name, "description": self._required_text(item, "description"), "parameters": parameters}
            triggers = item.get("triggers")
            if triggers:
                schema["triggers"] = triggers
            tools[name] = RegisteredTool(schema=schema, meta={**item, "plugin_id": plugin_id, "plugin_name_zh": manifest.get("name_zh", plugin_id)}, handler=handler)

    @staticmethod
    def _required_text(data: dict[str, Any], key: str) -> str:
        value = str(data.get(key, "")).strip()
        if not value:
            raise ValueError(f"missing {key}")
        return value

    def schemas(self) -> list[dict[str, Any]]:
        self.refresh()
        with self._lock:
            return [tool.schema for tool in self._tools.values()]

    def list_tools(self) -> list[dict[str, str]]:
        self.refresh()
        with self._lock:
            return [{"name": name, "description": tool.schema["description"]} for name, tool in self._tools.items()]

    def settings_tools(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            return {
                "version": self.version,
                "tools": [
                {
                    "name": name,
                    "name_zh": tool.meta.get("name_zh", name),
                    "description_zh": tool.meta.get("description_zh", tool.schema["description"]),
                    "plugin_id": tool.meta["plugin_id"],
                    "plugin_name_zh": tool.meta["plugin_name_zh"],
                }
                    for name, tool in self._tools.items()
                ],
                "errors": self._errors,
            }

    def execute(self, call: dict[str, Any]) -> dict[str, Any]:
        self.refresh()
        name = str(call.get("name", ""))
        with self._lock:
            tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, "tool.error", {"name": name}, f"没有名为 {name} 的动作").as_dict()
        try:
            result = tool.handler(**dict(call.get("arguments") or {}))
            if not isinstance(result, ToolResult):
                raise TypeError("tool function must return ToolResult")
            if name == "list_tools" and result.ok:
                result.data = {"tools": self.list_tools()}
            return result.as_dict()
        except (TypeError, ValueError) as error:
            return ToolResult(False, "tool.error", {"name": name}, f"{name} 参数不正确：{error}").as_dict()

    def install_files(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        if not files:
            raise ValueError("请选择一个插件文件夹。")
        cleaned: list[tuple[PurePosixPath, str]] = []
        for item in files:
            path = PurePosixPath(str(item.get("path", "")))
            if not path.parts or path.is_absolute() or ".." in path.parts:
                raise ValueError("插件内包含无效路径。")
            cleaned.append((path, str(item.get("content", ""))))
        roots = {path.parts[0] for path, _ in cleaned if len(path.parts) > 1}
        root = roots.pop() if len(roots) == 1 else None
        relative = [(PurePosixPath(*path.parts[1:]) if root and path.parts[0] == root else path, content) for path, content in cleaned]
        manifest_text = next((content for path, content in relative if path.as_posix() == "manifest.json"), None)
        if manifest_text is None:
            raise ValueError("所选文件夹根目录缺少 manifest.json。")
        manifest = json.loads(manifest_text)
        plugin_id = self._required_text(manifest, "id")
        destination = self.plugins_path / plugin_id
        if destination.exists():
            raise ValueError(f"插件 {plugin_id} 已安装；请直接修改该文件夹以更新。")
        destination.mkdir(parents=True)
        for path, content in relative:
            if not path.parts or ".." in path.parts:
                raise ValueError("插件内包含无效路径。")
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.refresh(force=True)
        if any(error["plugin"] == plugin_id for error in self._errors):
            raise ValueError(next(error["message"] for error in self._errors if error["plugin"] == plugin_id))
        return {"ok": True, "plugin_id": plugin_id, "tools": self.settings_tools()}


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry


def tool_schemas() -> list[dict[str, Any]]:
    return _registry.schemas()


def execute(call: dict[str, Any]) -> dict[str, Any]:
    return _registry.execute(call)


def install_plugin_files(files: list[dict[str, Any]]) -> dict[str, Any]:
    return _registry.install_files(files)


def _limits(definition: dict[str, Any]) -> str:
    minimum, maximum = definition.get("minimum"), definition.get("maximum")
    return f"between {minimum} and {maximum}" if minimum is not None and maximum is not None else f"at least {minimum}" if minimum is not None else f"at most {maximum}"


def constraint_error(response: dict[str, Any]) -> dict[str, Any] | None:
    if response.get("error_code") != "truncated":
        return None
    reasoning = str(response.get("reasoning", ""))
    for schema in tool_schemas():
        for parameter, definition in schema["parameters"].get("properties", {}).items():
            if definition.get("minimum") is None and definition.get("maximum") is None:
                continue
            match = re.search(rf"\b{re.escape(parameter)}\s*(?:=|:)?\s*(-?\d+(?:\.\d+)?)", reasoning, re.I)
            if match and not (definition.get("minimum", float("-inf")) <= float(match.group(1)) <= definition.get("maximum", float("inf"))):
                value = float(match.group(1))
                return ToolResult(False, "tool.error", {"name": schema["name"], "parameter": parameter, "value": value}, f"{schema['name']}: {parameter} must be {_limits(definition)}.").as_dict()
    return None


def input_constraint_error(call: dict[str, Any], text: str) -> dict[str, Any] | None:
    name = str(call.get("name", ""))
    with _registry._lock:
        tool = _registry._tools.get(name)
    if tool is None:
        return None
    aliases = tool.meta.get("parameter_aliases", {})
    for parameter, definition in tool.schema["parameters"].get("properties", {}).items():
        if definition.get("minimum") is None and definition.get("maximum") is None:
            continue
        terms = "|".join(re.escape(alias) for alias in aliases.get(parameter, [parameter]))
        match = re.search(rf"\b(?:{terms})\s*(?:=|:)?\s*(-?\d+(?:\.\d+)?)", text, re.I)
        if match and not (definition.get("minimum", float("-inf")) <= float(match.group(1)) <= definition.get("maximum", float("inf"))):
            value = float(match.group(1))
            return ToolResult(False, "tool.error", {"name": name, "parameter": parameter, "value": value}, f"{name}: {parameter} must be {_limits(definition)}.").as_dict()
    return None
