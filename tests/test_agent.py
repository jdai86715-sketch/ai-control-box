import asyncio

import pytest

from app.agent import agent
from app.config import settings


def test_rules_route_time(monkeypatch):
    monkeypatch.setattr(settings, "ai_backend", "rules")

    call = asyncio.run(agent.plan("现在几点"))

    assert call.name == "get_time"
    assert call.arguments == {}


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ai_backend", "unsupported")

    with pytest.raises(ValueError, match="仅支持 llama_cpp 或 rules"):
        asyncio.run(agent.plan("现在几点"))


def test_model_json_can_be_extracted_from_markdown_fence():
    call = agent._extract_tool_call('```json\n{"name":"get_time","arguments":{}}\n```')

    assert call == {"name": "get_time", "arguments": {}}
