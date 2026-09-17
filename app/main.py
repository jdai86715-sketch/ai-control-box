from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.agent import agent
from app.audit import write_audit
from app.models import CommandRecord, CommandRequest, RiskLevel
from app.tools import registry
from app.tools import computer, hardware  # noqa: F401 - 注册默认工具

app = FastAPI(
    title="AI 智能控制盒",
    version="0.1.0",
    description="通过自然语言调用受控工具的本地自动化服务。中、高风险操作需要明确确认。",
)
commands: dict[str, CommandRecord] = {}


def execute(record: CommandRecord) -> CommandRecord:
    tool = registry.get(record.tool_call.name)
    record.result = tool.handler(record.tool_call.arguments)
    record.status = "已完成"
    write_audit("工具已执行", {"指令编号": record.id, "工具": tool.name, "风险等级": tool.risk, "结果": record.result})
    return record


@app.get("/health", summary="检查服务状态", description="确认 AI 智能控制盒服务是否正常运行。")
def health() -> dict[str, str]:
    return {"状态": "正常"}


@app.get("/tools", summary="查看可用工具", description="列出当前已注册工具及其风险等级。")
def tools() -> list[dict[str, str]]:
    return registry.list_public()


@app.post("/commands", response_model=CommandRecord, summary="提交自然语言指令", description="低风险操作会立即执行；中、高风险操作将等待确认。")
async def submit_command(request: CommandRequest) -> CommandRecord:
    try:
        tool_call = await agent.plan(request.text)
        tool = registry.get(tool_call.name)
    except Exception as exc:
        write_audit("指令已拒绝", {"原始指令": request.text, "原因": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = CommandRecord(text=request.text, tool_call=tool_call, risk=tool.risk, status="已规划")
    commands[record.id] = record
    write_audit("指令已规划", {"指令编号": record.id, "原始指令": record.text, "工具": tool.name, "风险等级": tool.risk})
    if tool.risk == RiskLevel.LOW:
        return execute(record)
    record.status = "等待确认"
    return record


@app.post("/commands/{command_id}/confirm", response_model=CommandRecord, summary="确认执行指令", description="仅执行处于“等待确认”状态的指令。")
def confirm_command(command_id: str) -> CommandRecord:
    record = commands.get(command_id)
    if not record:
        raise HTTPException(status_code=404, detail="指令不存在或服务已重启。")
    if record.status != "等待确认":
        raise HTTPException(status_code=409, detail="该指令当前不需要确认。")
    return execute(record)