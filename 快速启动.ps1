param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $project

if (-not (Test-Path ".\.run-venv\Scripts\python.exe")) {
    Write-Host "正在创建 Python 虚拟环境…" -ForegroundColor Cyan
    & $Python -m venv .run-venv
}

Write-Host "正在安装项目依赖…" -ForegroundColor Cyan
& ".\.run-venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env，请按需检查白名单和安全目录。" -ForegroundColor Yellow
}

Write-Host "请确认 llama.cpp 已在 http://127.0.0.1:8080 运行。" -ForegroundColor Yellow
Write-Host "正在启动控制盒： http://127.0.0.1:8000/docs" -ForegroundColor Cyan
& ".\.run-venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
