from fastapi.testclient import TestClient

from app import main
from app.config import settings


def test_health_endpoint():
    client = TestClient(main.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"状态": "正常"}


def test_medium_risk_command_waits_for_confirmation(monkeypatch):
    monkeypatch.setattr(settings, "ai_backend", "rules")
    monkeypatch.setattr(main, "write_audit", lambda *_: None)
    main.commands.clear()
    client = TestClient(main.app)

    response = client.post("/commands", json={"指令": "打开记事本"})

    assert response.status_code == 200
    body = response.json()
    assert body["执行计划"]["工具名称"] == "open_app"
    assert body["风险等级"] == "中"
    assert body["执行状态"] == "等待确认"
