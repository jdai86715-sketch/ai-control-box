from __future__ import annotations
import json
from typing import Any
from urllib.request import Request, urlopen

class ToolVectorIndex:
    def __init__(self, server_url: str, schemas: list[dict[str, Any]]) -> None:
        self.url, self.schemas = server_url.rstrip("/"), schemas
        self.vectors = [self._embed(json.dumps(item, ensure_ascii=False)) for item in schemas]
    def top_five(self, text: str) -> list[dict[str, Any]]:
        query=self._embed(text); scores=[sum(a*b for a,b in zip(query,v)) for v in self.vectors]
        return [self.schemas[i] for i in sorted(range(len(scores)), key=scores.__getitem__, reverse=True)[:5]]
    def _embed(self, text: str) -> list[float]:
        request=Request(self.url+"/embedding", data=json.dumps({"content":text}).encode(), headers={"Content-Type":"application/json"})
        with urlopen(request, timeout=30) as response: return json.loads(response.read())["embedding"]
