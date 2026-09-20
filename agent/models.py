import json
from pathlib import Path
from typing import Any

from .needle import NeedleModel
from .tools import get_registry, tool_schemas


TOOL_INDEX_PATH = Path(__file__).parent.parent / "models" / "needle-tools.idx"


class ModelRouter:
    """Keeps the web and tool layers independent from the selected model."""

    def __init__(self) -> None:
        self._model: NeedleModel | None = None
        self._tool_version = ""
        self._ensure_current()

    def _ensure_current(self) -> None:
        registry = get_registry()
        registry.refresh()
        if self._model is None or self._tool_version != registry.version:
            self._model = NeedleModel(tool_schemas(), str(TOOL_INDEX_PATH))
            self._tool_version = registry.version

    def plan(self, text: str) -> dict[str, Any]:
        self._ensure_current()
        assert self._model is not None
        return self._model.plan(text)

    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        self._ensure_current()
        assert self._model is not None
        return self._model.plan(json.dumps(results, ensure_ascii=False))

    def reset(self) -> None:
        self._ensure_current()
        assert self._model is not None
        self._model.reset()
