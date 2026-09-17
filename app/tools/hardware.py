from __future__ import annotations

import json
import socket
from typing import Any

from paho.mqtt import publish

from app.config import settings
from app.models import RiskLevel
from app.tools.registry import Tool, registry


ACTIONS = {
    "打开": "on",
    "开启": "on",
    "开": "on",
    "on": "on",
    "关闭": "off",
    "关": "off",
    "off": "off",
}


def control_device(arguments: dict[str, Any]) -> dict[str, Any]:
    device_name = str(arguments.get("device", "")).strip()
    requested_action = str(arguments.get("action", "")).strip().lower()
    action = ACTIONS.get(requested_action)
    device_id = settings.device_map.get(device_name)
    if not device_id:
        return {"成功": False, "说明": f"设备未获授权：{device_name}", "已授权设备": list(settings.device_map)}
    if not action:
        return {"成功": False, "说明": "仅允许打开或关闭设备。"}

    topic = f"{settings.mqtt_topic_prefix}/devices/{device_id}/set"
    payload = json.dumps({"device": device_id, "action": action}, ensure_ascii=False)
    try:
        with socket.create_connection((settings.mqtt_broker_host, settings.mqtt_broker_port), timeout=2):
            pass
        publish.single(
            topic,
            payload=payload,
            hostname=settings.mqtt_broker_host,
            port=settings.mqtt_broker_port,
            retain=False,
            keepalive=5,
        )
    except OSError:
        return {"成功": False, "说明": "无法连接 MQTT 服务器。请检查服务器地址、端口和网络。"}

    return {"成功": True, "说明": f"已发送{device_name}{'打开' if action == 'on' else '关闭'}指令", "MQTT主题": topic}


registry.register(Tool("control_device", "通过 MQTT 控制已授权硬件，例如打开或关闭客厅灯。", RiskLevel.MEDIUM, control_device))