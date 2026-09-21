from __future__ import annotations
import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

class QwenModel:
    def __init__(self, url: str, retriever: Any) -> None:
        self.url, self.retriever = url.rstrip("/"), retriever
    def plan(self, text: str) -> dict[str, Any]:
        tools = self.retriever.top_five(text)
        prompt = "只输出 JSON: {\"function_calls\":[{\"name\":...,\"arguments\":{...}}]}; 可用工具：" + json.dumps(tools, ensure_ascii=False) + "\n指令：" + text
        data = self._post("/completion", {"prompt": prompt, "n_predict": 384, "json_schema": {"type":"object"}})
        try: calls = json.loads(data.get("content", "{}")).get("function_calls", [])
        except json.JSONDecodeError: calls = []
        return {"function_calls": calls, "reasoning": "Qwen top-5 tool retrieval", "candidate_count": len(tools)}
    def feed_results(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        return self.plan(json.dumps(results, ensure_ascii=False))
    def reset(self) -> None: pass
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            request = Request(self.url + path, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
            with urlopen(request, timeout=30) as response: return json.loads(response.read())
        except (URLError, OSError, json.JSONDecodeError) as error: raise RuntimeError(f"Qwen llama-server 不可用：{error}")
