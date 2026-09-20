import json
from pathlib import Path
from typing import Any

from .needle import NeedleModel
from .tools import tool_schemas


TOOL_INDEX_PATH = Path(__file__).parent.parent / "models" / "needle-tools.idx"


class ModelRouter:
    """Keeps the web and tool layers independent from the selected model."""

    def __init__(self) -> None:
        self._model = NeedleModel(tool_schemas(), str(TOOL_INDEX_PATH))

    def plan(self, text: str) -> dict[str, Any]:
        return self._model.plan(text)

    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        return self._model.plan(json.dumps(results, ensure_ascii=False))

    def reset(self) -> None:
        self._model.reset()
