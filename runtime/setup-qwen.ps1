param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$runtime = Join-Path $ProjectRoot "runtime"
$models = Join-Path $ProjectRoot "models"
$serverDirectory = Join-Path $runtime "llama.cpp"
$serverZip = Join-Path $runtime "llama-bin-win-cpu-x64.zip"
$model = Join-Path $models "qwen2.5-1.5b-instruct-q4_k_m.gguf"

New-Item -ItemType Directory -Force -Path $runtime, $models | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $serverDirectory "llama-server.exe"))) {
    Invoke-WebRequest `
        -Uri "https://github.com/ggml-org/llama.cpp/releases/download/b11223/llama-b11223-bin-win-cpu-x64.zip" `
        -OutFile $serverZip
    Expand-Archive -LiteralPath $serverZip -DestinationPath $serverDirectory -Force
    Remove-Item -LiteralPath $serverZip
}

if (-not (Test-Path -LiteralPath $model)) {
    Invoke-WebRequest `
        -Uri "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf?download=true" `
        -OutFile $model
}

Write-Host "Qwen and llama.cpp are ready in this project."
