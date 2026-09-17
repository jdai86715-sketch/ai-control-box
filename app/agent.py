from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import settings
from app.models import ToolCall


class Agent:
    async def plan(self, text: str) -> ToolCall:
        backend = settings.ai_backend.lower()
        if backend in {"llama_cpp", "llama.cpp"}:
            return await self._plan_with_llama_cpp(text)
        if backend == "rules":
            return self._plan_with_rules(text)
        raise ValueError("AI_BACKEND 仅支持 llama_cpp 或 rules。")

    def _plan_with_rules(self, text: str) -> ToolCall:
        normalized = text.strip()
        if any(word in normalized for word in ("时间", "几点", "现在")):
            return ToolCall(name="get_time")
        if any(word in normalized for word in ("打开", "启动", "运行")):
            for app_name in settings.app_map:
                if app_name in normalized:
                    return ToolCall(name="open_app", arguments={"app_name": app_name})
        for device_name in settings.device_map:
            if device_name in normalized:
                if any(word in normalized for word in ("打开", "开启", "开")):
                    return ToolCall(name="control_device", arguments={"device": device_name, "action": "打开"})
                if any(word in normalized for word in ("关闭", "关")):
                    return ToolCall(name="control_device", arguments={"device": device_name, "action": "关闭"})
        if any(word in normalized for word in ("文件", "目录", "列出")):
            return ToolCall(name="list_files", arguments={"directory": str(settings.safe_paths[0])})
        raise ValueError("暂时无法安全地理解这条指令。请尝试：打开记事本、打开客厅灯、现在几点、列出文件。")

    def _tool_prompt(self, text: str) -> str:
        tools = [
            {"name": "get_time", "arguments": {}},
            {"name": "open_app", "arguments": {"app_name": "仅限已授权应用名称"}},
            {"name": "list_files", "arguments": {"directory": "仅限安全目录内路径"}},
            {"name": "control_device", "arguments": {"device": "仅限已授权设备名称", "action": "打开或关闭"}},
        ]
        return (
            "你是安全的本地工具路由器。只能从给定工具中选择一个；"
            "绝不能执行 shell 命令。只输出 JSON，不要 Markdown，对象形如"
            '{"name":"tool_name","arguments":{}}。\n'
            f"已授权应用：{list(settings.app_map)}\n已授权设备：{list(settings.device_map)}\n"
            f"可用工具：{json.dumps(tools, ensure_ascii=False)}\n用户：{text}"
        )

    async def _plan_with_llama_cpp(self, text: str) -> ToolCall:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.llama_cpp_url.rstrip('/')}/v1/chat/completions",
                json={
                    "model": settings.llama_cpp_model,
                    "messages": [
                        {"role": "system", "content": self._tool_prompt("")},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0,
                    "max_tokens": 200,
                },
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"].get("content", "")
        return self._sanitize_tool_call(ToolCall.model_validate(self._extract_tool_call(str(content))))

    @staticmethod
    def _sanitize_tool_call(call: ToolCall) -> ToolCall:
        # 模型可能会臆造路径；文件工具只能浏览配置中的安全目录。
        if call.name == "list_files":
            call.arguments["directory"] = str(settings.safe_paths[0])
        if call.name == "control_device":
            if call.arguments.get("device") not in settings.device_map:
                raise ValueError("模型选择了未授权的硬件设备。")
            if call.arguments.get("action") not in ("打开", "关闭", "开", "关", "on", "off"):
                raise ValueError("模型选择了未授权的硬件动作。")
        return call
    @staticmethod
    def _extract_tool_call(content: str) -> dict[str, Any]:
        cleaned = content.strip().replace("```json", "").replace("```", "").strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("本地模型未返回有效的工具 JSON。")
        return json.loads(cleaned[start : end + 1])


agent = Agent()
