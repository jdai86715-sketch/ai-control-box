"""The small boundary between this application and Needle's runtime package."""

from typing import Any

import needle


class NeedleModel:
    def __init__(self, tools: list[dict[str, Any]], tool_index_path: str) -> None:
        self._agent = needle.Needle(tools=tools, generation=3, tool_index_path=tool_index_path)

    def plan(self, text: str) -> dict[str, Any]:
        return self._agent.complete(text)

    def reset(self) -> None:
        self._agent.reset()
