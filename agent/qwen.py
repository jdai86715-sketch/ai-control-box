from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .runtime_manager import RuntimeManager


class QwenModel:
    """One Qwen agent turn: natural reply and optional tool calls share one context."""

    def __init__(self, runtime: RuntimeManager, model_id: str, schemas: Callable[[], list[dict[str, Any]]]) -> None:
        self._runtime = runtime
        self._model_id = model_id
        self._schemas = schemas
        self._messages: list[dict[str, Any]] = []
        self._pending_calls: list[dict[str, Any]] = []

    def plan(self, text: str) -> dict[str, Any]:
        if not self._messages:
            self._messages = [
                {"role": "system", "content": "你当前运行在 AI 控制盒环境。每条输入都是独立的单轮。你可以直接回答，也可以主动调用提供的工具：当用户要求执行动作，或回答需要当前真实状态时，调用合适工具；普通问题直接回答。当前时间、天气、设备状态不能凭空回答。工具存在不等于必须调用；list_tools 只用于用户明确要求工具名称或工具清单。工具完成后，依据结果自然回答用户；仅在确实需要下一步信息或动作时继续调用。"},
            ]
        self._messages.append({"role": "user", "content": text})
        return self._complete("Qwen native tools")

    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        for call, result in zip(self._pending_calls, results):
            self._messages.append({"role": "tool", "tool_call_id": call["tool_call_id"], "content": json.dumps(result, ensure_ascii=False)})
        return self._complete("Qwen native tool results")

    def reset(self) -> None:
        self._messages = []
        self._pending_calls = []

    def _complete(self, reasoning: str) -> dict[str, Any]:
        data = self._post("/v1/chat/completions", {"messages": self._messages, "tools": [{"type": "function", "function": schema} for schema in self._schemas()], "tool_choice": "auto", "temperature": 0, "max_tokens": 512})
        message = dict(data["choices"][0]["message"])
        message["content"] = str(message.get("content") or "")
        self._messages.append(message)
        calls = self._native_calls(message.get("tool_calls") or [])
        self._pending_calls = calls
        return {"reply": message["content"], "function_calls": calls, "reasoning": reasoning, "decode_tps": None}

    @staticmethod
    def _native_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            try:
                arguments = json.loads(str(function.get("arguments") or "{}"))
            except json.JSONDecodeError:
                arguments = None
            if isinstance(arguments, dict) and str(function.get("name", "")).strip() and str(tool_call.get("id", "")).strip():
                calls.append({"name": str(function["name"]), "arguments": arguments, "tool_call_id": str(tool_call["id"])})
        return calls

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            url = self._runtime.ensure_server(self._model_id) + path
            request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read())
        except (URLError, OSError, KeyError, IndexError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Qwen 不可用：{error}") from error
