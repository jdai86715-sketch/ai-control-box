param(
    [Parameter(Mandatory=$true)][string]$模型路径,
    [string]$llamaServer = "llama-server.exe",
    [int]$端口 = 8080
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command $llamaServer -ErrorAction SilentlyContinue) -and -not (Test-Path $llamaServer)) {
    throw "找不到 llama-server.exe，请先安装或指定完整路径。"
}
Write-Host "正在启动 llama.cpp，模型：$模型路径" -ForegroundColor Cyan
& $llamaServer -m $模型路径 --host 127.0.0.1 --port $端口 --ctx-size 4096