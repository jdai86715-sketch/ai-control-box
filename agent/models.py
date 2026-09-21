import json
from pathlib import Path
from typing import Any

from .needle import NeedleModel
from .qwen import QwenModel
from .config import get_model_settings
from .runtime_manager import RuntimeManager
from .tools import get_registry, tool_schemas


TOOL_INDEX_PATH = Path(__file__).parent.parent / "models" / "needle-tools.idx"


class ModelRouter:
    """Keeps the web and tool layers independent from the selected model."""

    def __init__(self, runtime: RuntimeManager) -> None:
        self._runtime = runtime
        self._model: Any | None = None
        self._tool_version = ""
        self._active_model = ""
        self._ensure_current()

    def _ensure_current(self) -> None:
        registry = get_registry()
        registry.refresh()
        settings = get_model_settings()
        if self._model is None or self._tool_version != registry.version or self._active_model != settings["active_model"]:
            self._model = NeedleModel(tool_schemas(), str(TOOL_INDEX_PATH)) if settings["active_model"] == "needle" else QwenModel(self._runtime, settings["qwen"]["model_id"], tool_schemas)
            self._tool_version = registry.version
            self._active_model = settings["active_model"]

    def plan(self, text: str) -> dict[str, Any]:
        self._ensure_current()
        assert self._model is not None
        return self._model.plan(text)

    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        self._ensure_current()
        assert self._model is not None
        return self._model.feed_results(results)

    def reset(self) -> None:
        self._ensure_current()
        assert self._model is not None
        self._model.reset()
