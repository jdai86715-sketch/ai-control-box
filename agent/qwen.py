from __future__ import annotations

import json
from typing import Any, Callable, Generator
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import get_settings
from .runtime_manager import RuntimeManager


class QwenModel:
    """One Qwen agent turn: natural reply and optional tool calls share one context."""

    _BASE_INSTRUCTION = "你运行在 AI 控制盒的单轮对话中。普通问题直接回答；需要当前真实信息或执行动作时使用提供的工具。不要编造真实状态。工具结果后，必要时继续调用工具；任务完成后自然回答。"
    _TOOL_CALL_INSTRUCTION = "当提供的工具能完成用户明确请求时，直接返回 native tool_call；不要用文字声称自己不能调用工具。"

    def __init__(self, runtime: RuntimeManager, model_id: str, schemas: Callable[[str], list[dict[str, Any]]]) -> None:
        self._runtime = runtime
        self._model_id = model_id
        self._schemas = schemas
        self._messages: list[dict[str, Any]] = []
        self._pending_calls: list[dict[str, Any]] = []
        self._active_schemas: list[dict[str, Any]] = []
        self._user_request = ""

    def plan(self, text: str) -> dict[str, Any]:
        self._active_schemas = self._schemas(text)
        self._start_turn()
        self._user_request = text
        self._messages.append({"role": "user", "content": text})
        return self._complete("Qwen native tools")

    def plan_stream(self, text: str) -> Generator[dict[str, Any], None, dict[str, Any]]:
        self._active_schemas = self._schemas(text)
        self._start_turn()
        self._user_request = text
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
        self._active_schemas = []
        self._user_request = ""

    def keep_pending_calls(self, count: int) -> None:
        """Discard calls emitted before a result-required tool returned."""
        self._pending_calls = self._pending_calls[:count]
        for message in reversed(self._messages):
            if message.get("role") == "assistant" and "tool_calls" in message:
                message["tool_calls"] = list(message["tool_calls"])[:count]
                return

    def _start_turn(self) -> None:
        if not self._messages:
            instruction = self._BASE_INSTRUCTION
            if self._active_schemas:
                instruction += self._TOOL_CALL_INSTRUCTION
            if any(schema.get("name") == "get_weather" for schema in self._active_schemas):
                location = get_settings()["location"]
                instruction += (
                    f" 默认天气位置是{location['city']}（{location['latitude']}, {location['longitude']}）。"
                    "用户没有指定地点时，调用 get_weather 且不传 location_id；"
                    "用户指定地点时，先调用 search_location，再把返回的 location_id 传给 get_weather；绝不能编造 location_id。"
                )
            self._messages = [
                {"role": "system", "content": instruction},
            ]

    def _append_results(self, results: list[dict[str, Any]]) -> None:
        for call, result in zip(self._pending_calls, results):
            self._messages.append({"role": "tool", "tool_call_id": call["tool_call_id"], "content": json.dumps(result, ensure_ascii=False)})
        for result in results:
            continuation = (result.get("data") or {}).get("agent_continuation") if isinstance(result, dict) else None
            if isinstance(continuation, dict):
                self._inject_continuation(continuation)

    def _inject_continuation(self, continuation: dict[str, Any]) -> None:
        tool = str(continuation.get("tool", "")).strip()
        arguments = continuation.get("arguments")
        if not tool or not isinstance(arguments, dict) or not self._messages:
            return
        instruction = (
            f" 原用户任务：{self._user_request}。已完成前一步工具调用。"
            f"任务尚未完成：现在调用 {tool}，必须包含已解析参数 "
            f"{json.dumps(arguments, ensure_ascii=False)}；保留原任务中要求的其他参数。"
            "拿到该工具结果前不要回答或猜测。"
        )
        self._messages[0]["content"] += instruction

    def _complete(self, reasoning: str) -> dict[str, Any]:
        body: dict[str, Any] = {"messages": self._messages, "temperature": 0, "max_tokens": 512}
        prompt_context = self._prompt_context()
        if self._active_schemas:
            body.update({"tools": [{"type": "function", "function": schema} for schema in self._active_schemas], "tool_choice": "auto"})
        data = self._post("/v1/chat/completions", body)
        message = dict(data["choices"][0]["message"])
        message["content"] = str(message.get("content") or "")
        self._messages.append(message)
        calls = self._calls_from_message(message)
        self._pending_calls = calls
        return {"reply": message["content"], "function_calls": calls, "reasoning": reasoning, "decode_tps": None, "prompt_context": prompt_context}

    def _complete_stream(self, reasoning: str) -> Generator[dict[str, Any], None, dict[str, Any]]:
        content: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        body: dict[str, Any] = {
            "messages": self._messages,
            "temperature": 0,
            "max_tokens": 512,
            "stream": True,
        }
        prompt_context = self._prompt_context()
        if self._active_schemas:
            body.update({
                "tools": [{"type": "function", "function": schema} for schema in self._active_schemas],
                "tool_choice": "auto",
                "parallel_tool_calls": False,
            })
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
        calls = self._calls_from_message(message)
        self._pending_calls = calls
        return {"reply": message["content"], "function_calls": calls, "reasoning": reasoning, "decode_tps": None, "prompt_context": prompt_context}

    def _prompt_context(self) -> dict[str, Any]:
        """A display-only snapshot of what this request sends to Qwen."""
        return {
            "system_prompt": str(self._messages[0].get("content", "")) if self._messages else "",
            "tool_names": [str(schema.get("name", "")) for schema in self._active_schemas],
        }

    def _calls_from_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        calls = self._native_calls(message.get("tool_calls") or [])
        if calls:
            return calls
        parsed = self._text_calls(str(message.get("content") or ""))
        if not parsed:
            return []
        wire_calls = [
            {
                "id": f"text-call-{len(self._messages)}-{index}",
                "type": "function",
                "function": {"name": call["name"], "arguments": json.dumps(call["arguments"], ensure_ascii=False)},
            }
            for index, call in enumerate(parsed)
        ]
        message["content"] = ""
        message["tool_calls"] = wire_calls
        return self._native_calls(wire_calls)

    @staticmethod
    def _text_calls(content: str) -> list[dict[str, Any]]:
        """Accept only a complete JSON tool-call payload, never prose fragments."""
        text = content.strip()
        if text.startswith("```") and text.endswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        candidates = payload.get("function_calls", []) if isinstance(payload, dict) and "function_calls" in payload else payload
        if isinstance(candidates, dict):
            candidates = [candidates]
        if not isinstance(candidates, list):
            return []
        calls: list[dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict):
                return []
            name, arguments = item.get("name"), item.get("arguments")
            if not isinstance(name, str) or not name.strip() or not isinstance(arguments, dict):
                return []
            calls.append({"name": name.strip(), "arguments": arguments})
        return calls

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
