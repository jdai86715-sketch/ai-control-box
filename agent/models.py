import json
from pathlib import Path
from typing import Any

from .qwen import QwenModel
from .tool_index import ToolVectorIndex
from .config import get_model_settings
from .tools import get_registry, qwen_tool_schemas, tool_schemas


TOOL_INDEX_PATH = Path(__file__).parent.parent / "models" / "needle-tools.idx"


class ModelRouter:
    """Keeps the web and tool layers independent from the selected model."""

    def __init__(self) -> None:
        self._model: Any | None = None
        self._tool_version = ""
        self._active_model = ""
        self._ensure_current()

    def _ensure_current(self) -> None:
        registry = get_registry()
        registry.refresh()
        settings = get_model_settings()
        if self._model is None or self._tool_version != registry.version or self._active_model != settings["active_model"]:
            if settings["active_model"] == "needle":
                from .needle import NeedleModel
                self._model = NeedleModel(tool_schemas(), str(TOOL_INDEX_PATH))
            else:
                self._model = QwenModel(settings["qwen"]["llama_server_url"], ToolVectorIndex(settings["qwen"]["embedding_server_url"], qwen_tool_schemas()))
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
