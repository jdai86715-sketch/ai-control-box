from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"


class CommandRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(
        min_length=1,
        max_length=2000,
        description="使用自然语言描述需要完成的任务。",
        validation_alias=AliasChoices("text", "指令"),
        serialization_alias="指令",
    )


class ToolCall(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(serialization_alias="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, serialization_alias="工具参数")


class CommandRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()), serialization_alias="指令编号")
    text: str = Field(serialization_alias="原始指令")
    tool_call: ToolCall = Field(serialization_alias="执行计划")
    risk: RiskLevel = Field(serialization_alias="风险等级")
    status: str = Field(serialization_alias="执行状态")
    result: dict[str, Any] | None = Field(default=None, serialization_alias="执行结果")