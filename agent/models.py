from typing import Any

from .needle import NeedleModel
from .tools import select_tools, tool_schemas


class ModelRouter:
    """Keeps the web and tool layers independent from the selected model."""

    def __init__(self) -> None:
        self._models: dict[tuple[str, ...], NeedleModel] = {}

    def plan(self, text: str) -> dict[str, Any]:
        names = select_tools(text)
        if not names:
            return {"type": "call", "function_calls": [], "selected_tools": []}
        key = tuple(names)
        model = self._models.get(key)
        if model is None:
            model = NeedleModel(tool_schemas(names))
            self._models[key] = model
        response = model.plan(text)
        response["selected_tools"] = names
        return response

    def reset(self) -> None:
        for model in self._models.values():
            model.reset()
