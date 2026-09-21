# Qwen 本地运行时：第一阶段

## 目标

让 Windows 上的 AI 控制盒在选择 Qwen 时可自动准备并启动本地 `llama-server`，并在服务或模型不可用时保持 WebUI 可启动、返回清晰错误。

## 范围

- 保留 Needle 现有运行路径和动态工具注册表。
- `requirements.txt` 继续只放 Python 依赖；不安装 `llama-cpp-python`。
- 新增 `runtime/` 运行时目录及固定版本的运行时清单，按 Windows x64、Linux x64、Linux ARM64 选择预编译 `llama-server` 包。
- 启动时检查本地二进制；缺失时下载、校验 SHA-256、解压完整发行包。
- Qwen 被选择且收到首条请求时，按当前选中的 GGUF 启动聊天服务、等待健康检查，然后发出请求。
- Qwen 不可用时，HTTP 接口返回中文错误；WebUI 继续运行，Needle 仍可在设置中切换使用。
- 模型文件仍由用户手动放入 `models/`；本阶段不下载或提交模型权重。

## 明确不做

- 不接入 embedding 模型、向量索引、知识库或 `tool_search`。
- 不改动插件 manifest、ToolRegistry 的最终执行规则或增加候选工具白名单。
- 不增加审计日志、自动重试、账户、网络远程控制或模型下载页面。
- 不让启动脚本自动编译 llama.cpp 或安装系统编译器。

## 结构

```text
runtime/
  manifest.json             # 平台、固定版本、下载地址与 SHA-256
  bin/<platform>/           # 自动解压后的 llama-server 与配套运行库
agent/
  runtime_manager.py        # 下载、校验、启动、健康检查、停止
  qwen.py                   # 仅通过本机 HTTP 调用聊天服务
settings/models.json        # active_model、Qwen 模型 id 与运行参数
```

## 调用流程

```text
选择 Qwen
  -> WebUI 仍正常启动
  -> 首条 Qwen 指令
  -> RuntimeManager 确认 llama-server
  -> 检查所选 GGUF
  -> 拉起 localhost 聊天服务并等待 /health
  -> Qwen 输出 JSON function_calls
  -> 既有 ToolRegistry 按 name 查找并执行
```

## 错误行为

- 不支持的平台、下载校验失败、二进制无法启动、模型文件缺失、健康检查超时：返回明确中文错误，不退出 WebUI 进程。
- 已有服务仅在它属于本应用管理的进程时停止；不结束其他进程。

## 验收

1. Windows x64 缺少运行时时，能下载/展开运行时；已有运行时时不重复下载。
2. 选择 Needle 时，不需要 llama-server，现有工具调用保持可用。
3. 选择已有 Qwen GGUF 时，服务成功启动且健康检查通过。
4. Qwen 服务或模型不可用时，网页显示错误而不闪退。
5. Qwen 的最小中文指令能返回并执行一个 JSON 工具调用。
