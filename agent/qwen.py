from __future__ import annotations
import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

class QwenModel:
    def __init__(self, url: str, retriever: Any) -> None:
        self.url, self.retriever = url.rstrip("/"), retriever
        self._original_instruction = ""
        self._city_follow_up_used = False

    def plan(self, text: str) -> dict[str, Any]:
        self._original_instruction = text
        self._city_follow_up_used = False
        response = self._complete(text, "用户指令")
        location_calls = [
            call for call in response["function_calls"]
            if call.get("name") in {"resolve_city", "get_device_location"}
        ]
        # A location lookup is a dependency, so never execute a model-guessed
        # weather call in the same step.
        if location_calls:
            response["function_calls"] = location_calls
        return response

    def _complete(self, text: str, label: str, allowed_tools: set[str] | None = None) -> dict[str, Any]:
        tools = self.retriever.top_five(text)
        prompt = (
            "根据请求调用一个或多个可用工具。仅输出 JSON：{\"function_calls\":[{\"name\":\"工具名\",\"arguments\":{}}]}。"
            "设备天气：先 get_device_location，再 get_weather。城市天气：先 resolve_city，再 get_weather。"
            "设备映射：控制盒=control_box；卧室传感器或卧室设备=bedroom_sensor；客厅传感器或客厅设备=living_room_sensor。"
            "关灯 brightness=0；关风扇 level=0。房间用 bedroom、living room 或 kitchen。"
            "\n工具："
            + json.dumps(tools, ensure_ascii=False)
            + f"\n{label}："
            + text
        )
        data = self._post(
            "/v1/chat/completions",
            {
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 384,
                "temperature": 0,
            },
        )
        choices = data.get("choices") or [{}]
        content = data.get("content") or choices[0].get("message", {}).get("content") or choices[0].get("text", "{}")
        try: calls = json.loads(content).get("function_calls", [])
        except json.JSONDecodeError: calls = []
        if not isinstance(calls, list):
            calls = []
        if allowed_tools is not None:
            calls = [call for call in calls if call.get("name") in allowed_tools]
        return {"function_calls": calls, "reasoning": "Qwen 中文工具检索", "candidate_count": len(tools)}
    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        # A resolved city is the only supported dependent workflow.  Limiting
        # the continuation prevents stateless completions from repeating an
        # already executed device action.
        location_events = {"city.resolve", "device.location.read"}
        if self._city_follow_up_used or not any(result.get("event") in location_events and result.get("ok") for result in results):
            return {"function_calls": [], "reasoning": "Qwen 工具调用已完成"}
        self._city_follow_up_used = True
        context = json.dumps({"original_instruction": self._original_instruction, "tool_results": results}, ensure_ascii=False)
        return self._complete(context, "城市或设备定位结果；请继续完成原始天气查询", {"get_weather"})

    def reset(self) -> None:
        self._original_instruction = ""
        self._city_follow_up_used = False
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            request = Request(self.url + path, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
            with urlopen(request, timeout=30) as response: return json.loads(response.read())
        except (URLError, OSError, json.JSONDecodeError) as error: raise RuntimeError(f"Qwen llama-server 不可用：{error}")
