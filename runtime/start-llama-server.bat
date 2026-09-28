@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "SERVER=%~dp0llama.cpp\llama-server.exe"
set "MODEL=%PROJECT_ROOT%\models\qwen2.5-1.5b-instruct-q4_k_m.gguf"

if not exist "%SERVER%" (
  echo llama.cpp server is missing from runtime\llama.cpp.
  exit /b 1
)
if not exist "%MODEL%" (
  echo Qwen model is missing from models.
  exit /b 1
)

echo Starting local Qwen service on http://127.0.0.1:8080
"%SERVER%" -m "%MODEL%" --embedding --host 127.0.0.1 --port 8080
