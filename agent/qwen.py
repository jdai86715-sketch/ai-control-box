from __future__ import annotations

import json
from typing import Any, Callable, Generator
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
        self._start_turn()
        self._messages.append({"role": "user", "content": text})
        return self._complete("Qwen native tools")

    def plan_stream(self, text: str) -> Generator[dict[str, Any], None, dict[str, Any]]:
        self._start_turn()
        self._messages.append({"role": "user", "content": text})
        return (yield from self._complete_stream("Qwen native tools"))

    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        self._append_results(results)
        return self._complete("Qwen native tool results")

    def feed_results_stream(self, results: list[dict[str, Any]]) -> Generator[dict[str, Any], None, dict[str, Any]]:
        self._append_results(results)
        return (yield from self._complete_stream("Qwen native tool results"))

    def reset(self) -> None:
        self._messages = []
        self._pending_calls = []

    def _start_turn(self) -> None:
        if not self._messages:
            self._messages = [
                {"role": "system", "content": "你当前运行在 AI 控制盒环境。每条输入都是独立的单轮。你可以直接回答，也可以主动调用提供的工具：当用户要求执行动作，或回答需要当前真实状态时，调用合适工具；普通问题直接回答。当前时间、天气、设备状态不能凭空回答。工具存在不等于必须调用；list_tools 只用于用户明确要求工具名称或工具清单。工具完成后，依据结果自然回答用户；仅在确实需要下一步信息或动作时继续调用。"},
            ]

    def _append_results(self, results: list[dict[str, Any]]) -> None:
        for call, result in zip(self._pending_calls, results):
            self._messages.append({"role": "tool", "tool_call_id": call["tool_call_id"], "content": json.dumps(result, ensure_ascii=False)})

    def _complete(self, reasoning: str) -> dict[str, Any]:
        data = self._post("/v1/chat/completions", {"messages": self._messages, "tools": [{"type": "function", "function": schema} for schema in self._schemas()], "tool_choice": "auto", "temperature": 0, "max_tokens": 512})
        message = dict(data["choices"][0]["message"])
        message["content"] = str(message.get("content") or "")
        self._messages.append(message)
        calls = self._native_calls(message.get("tool_calls") or [])
        self._pending_calls = calls
        return {"reply": message["content"], "function_calls": calls, "reasoning": reasoning, "decode_tps": None}

    def _complete_stream(self, reasoning: str) -> Generator[dict[str, Any], None, dict[str, Any]]:
        content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        body = {
            "messages": self._messages,
            "tools": [{"type": "function", "function": schema} for schema in self._schemas()],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "temperature": 0,
            "max_tokens": 512,
            "stream": True,
        }
        for data in self._post_stream("/v1/chat/completions", body):
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content")
            if text:
                value = str(text)
                content.append(value)
                yield {"type": "text_delta", "text": value}
            for item in delta.get("tool_calls") or []:
                index = int(item.get("index", 0))
                call = tool_calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if item.get("id"):
                    call["id"] = str(item["id"])
                function = item.get("function") or {}
                if function.get("name"):
                    call["function"]["name"] += str(function["name"])
                if function.get("arguments"):
                    call["function"]["arguments"] += str(function["arguments"])
        message: dict[str, Any] = {"role": "assistant", "content": "".join(content)}
        if tool_calls:
            message["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
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

    def _post_stream(self, path: str, body: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        try:
            url = self._runtime.ensure_server(self._model_id) + path
            request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
            with urlopen(request, timeout=120) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        return
                    yield json.loads(payload)
        except (URLError, OSError, KeyError, IndexError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Qwen 不可用：{error}") from error
