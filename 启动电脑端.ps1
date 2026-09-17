$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project
$python = @(
    ".\.run-venv\Scripts\python.exe",
    ".\.venv\Scripts\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    Write-Host "尚未创建可用 Python 虚拟环境，请先运行：.\快速启动.ps1" -ForegroundColor Yellow
    exit 1
}
Write-Host "正在启动 AI 智能控制盒： http://127.0.0.1:8000/docs" -ForegroundColor Cyan
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
