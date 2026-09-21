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
- 模型目录内置 Hugging Face 下载信息；普通用户可在设置内下载模型，不必手动放置 GGUF。模型权重仍不提交 Git。
- 设置弹窗顶部使用紧凑标签：`常规`、`下载`、`模型` 和关闭图标。

## 明确不做

- 不接入 embedding 模型、向量索引、知识库或 `tool_search`。
- 不改动插件 manifest、ToolRegistry 的最终执行规则或增加候选工具白名单。
- 不增加审计日志、自动重试、账户或网络远程控制。
- 不在应用启动时预下载 llama-server 或任一 Qwen 模型；只使用 Needle 的用户不额外下载运行时和模型。
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
models/catalog.json         # Hugging Face 模型 id、文件、大小、SHA-256 与下载 URL
```

## 设置体验

- `常规` 保留城市、纬度、经度和工具目录。
- `模型` 只列出模型名称与安装状态。例如 `qwen2.5-1.5b-instruct-q4_k_m [未安装]`；不展示模型大小、路径、端口或技术提示。
- 在模型页点击未安装模型，自动切换至本弹窗的 `下载` 标签。
- `下载` 只列出可下载模型和 `下载` 控件；用户点击后从 Hugging Face 拉取，展示进度。暂停或中断后应可续传。
- 用户在下载页点击 Qwen 模型时，如对应平台的 llama-server 运行时尚未准备，先弹出一次确认：`使用 Qwen 需要 llama-server，是否下载依赖？`。确认后先准备运行时，再自动继续下载该模型；取消则不下载任何内容。
- llama-server 是 Qwen 的实现依赖，不作为普通模型条目显示；只使用 Needle 的用户不会看到或下载它。
- 已安装模型可在模型页选择为当前模型；选择 Qwen 后，首次指令才准备 llama-server 并启动它。
- llama-server URL、embedding URL 等实现细节不出现在普通设置页。

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
2. 只使用 Needle 时，不下载 llama-server 或任一 Qwen 模型，现有工具调用保持可用。
3. 模型页的未安装项点击后切换到下载页；下载页可以从 Hugging Face 下载并续传 GGUF。
4. 选择已安装 Qwen GGUF 时，服务成功启动且健康检查通过。
5. Qwen 服务或模型不可用时，网页显示错误而不闪退。
6. Qwen 的最小中文指令能返回并执行一个 JSON 工具调用。
