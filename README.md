# AI 智能控制盒

> **v0.1.0 · 本地 llama.cpp + 安全工具调用**

一个在本机运行的 AI 自动化原型。它把中文指令转换为**受控工具调用**，而不是让模型直接执行任意命令。

```text
自然语言 → llama.cpp 理解 → 工具选择 → 白名单校验 → 用户确认 → 执行 → 审计记录
```

## 当前能力

- 使用本机 [llama.cpp](https://github.com/ggerganov/llama.cpp) 的 OpenAI 兼容接口理解指令。
- 获取本机时间、浏览受限目录、启动白名单 Windows 应用。
- 为中、高风险操作提供明确的二次确认。
- 将规划、拒绝和执行结果记录到审计日志。
- 预留 MQTT 设备控制工具；未连接真实设备时请勿确认硬件操作。

## 快速启动（Windows）

### 1. 前置条件

- Python 3.11 或以上，安装时勾选 **Add Python to PATH**。
- 已安装 `llama-server.exe`。
- 一个 GGUF 指令模型，例如 Qwen2.5 1.5B Instruct。

### 2. 创建环境并安装依赖

```powershell
cd <项目目录>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### 3. 启动 llama.cpp

在第一个 PowerShell 窗口运行：

```powershell
.\启动llama.cpp.ps1 -模型路径 "<模型文件路径>" -llamaServer "<llama-server.exe 路径>"
```

确认 `http://127.0.0.1:8080/health` 可访问。

### 4. 启动控制盒

在第二个 PowerShell 窗口运行：

```powershell
.\启动电脑端.ps1
```

打开 Swagger 测试界面：<http://127.0.0.1:8000/docs>。

也可以使用 `快速启动.ps1` 完成依赖安装后启动控制盒；它仍需要先在另一个窗口启动 llama.cpp。

## 试一试

向 `POST /commands` 提交：

```json
{"指令":"现在几点"}
```

或：

```json
{"指令":"打开记事本"}
```

“打开记事本”会返回 `等待确认`。复制响应中的 `指令编号`，再调用：

```text
POST /commands/{指令编号}/confirm
```

## 安全边界

这是本项目最重要的部分：

- 模型只能选择已注册的工具，不能运行自然语言中出现的任意 Shell 命令。
- 应用仅能从 `.env` 的 `ALLOWED_APPS` 白名单启动。
- 文件仅能在 `SAFE_DIRECTORIES` 范围内浏览。
- 中、高风险工具必须经过确认接口。
- 每次规划、拒绝和执行都会写入 `data/audit.log`。

本项目不使用 Ollama；模型服务只使用 llama.cpp。`AI_BACKEND=rules` 仅用于不启动模型时验证接口与安全流程。

## 配置

复制 `.env.example` 为 `.env` 后，至少核对：

```text
AI_BACKEND=llama_cpp
LLAMA_CPP_URL=http://127.0.0.1:8080
LLAMA_CPP_MODEL=local-model
ALLOWED_APPS=记事本=notepad.exe,计算器=calc.exe
SAFE_DIRECTORIES=C:\\Users\\你的用户名\\Desktop
```

MQTT 配置只在连接了真实 Broker 和设备后再启用。请先使用 LED 或继电器测试，并始终保留确认机制。

## API 概览

| 接口 | 用途 |
| --- | --- |
| `GET /health` | 检查控制盒服务状态 |
| `GET /tools` | 查看已注册工具和风险等级 |
| `POST /commands` | 规划并执行低风险指令，或返回待确认指令 |
| `POST /commands/{command_id}/confirm` | 确认执行中、高风险指令 |

## 开发与测试

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

GitHub Actions 会在每次推送和拉取请求时运行测试。

## 截图

真实界面截图的采集要求见 [docs/screenshots/README.md](docs/screenshots/README.md)。截图不应包含 API 密钥、用户名、私有文件名或真实设备地址。

## 路线图

- [x] v0.1.0：本地 llama.cpp + 安全工具调用
- [ ] ESP32 + MQTT 真实灯控演示
- [ ] Android / Termux 适配
- [ ] 可扩展插件体系与贡献者指南

## 许可证

本项目以 [MIT License](LICENSE) 发布。
