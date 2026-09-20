# AI 控制盒

一个在 Windows 上运行的本地工具调用原型。页面接收一句指令，Needle 只输出结构化工具调用，Python 再从已注册工具表中执行对应函数，并把固定中文结果显示回页面。

它不是聊天模型：Needle 3 的职责只是把指令变成 `name + arguments` JSON。

## 启动

双击 [run.bat](run.bat)，首次启动会创建 `.venv` 并安装 `requirements.txt` 中的依赖；浏览器会自动打开本地页面。

也可以在项目根目录执行：

```cmd
run.bat
```

服务使用随机可用端口，因此每次启动时浏览器地址可能不同。

## 目录

```text
ai-control-box/
├─ run.bat                     # Windows 启动入口
├─ main.py                     # 仅启动 Web 服务
├─ settings/
│  └─ environment.json         # 城市、经纬度等可修改环境信息
├─ agent/
│  ├─ web.py                   # WebUI、/api/chat 与 /api/settings
│  ├─ models.py                # 工具候选 → Needle 模型实例
│  ├─ needle.py                # 唯一的 Needle 适配边界
│  ├─ config.py                # 读写 settings/environment.json
│  ├─ tools/
│  │  ├─ __init__.py           # 工具注册表、schema、筛选、执行
│  │  ├─ device.py             # 模拟灯、风扇、室温
│  │  ├─ environment.py        # 系统时间、Open-Meteo 天气
│  │  └─ tool_index.json       # 工具的中英文检索词
│  └─ static/                  # 单页纯黑 WebUI 与图标
└─ models/                     # 预留给未来手动放置 .cact 权重
```

## 实际调用流程

```mermaid
flowchart TD
    A[用户输入] --> B[web.py: ControlBox.chat]
    B --> C[tools/tool_index.json: 检索词匹配]
    C --> D[命中少量工具名]
    D --> E[tool_schemas(names): 只取候选 schema]
    E --> F[NeedleModel: 注入候选 schema]
    F --> G[Needle.complete: function_calls JSON]
    G --> H[execute: 按注册表 name 找 Python 函数]
    H --> I[ToolResult: 固定中文反馈]
    I --> J[WebUI 显示 JSON 与结果]
```

例如输入 `turn on the bedroom light to 20 percent`：

1. 索引命中 `set_light`，而不是把所有工具定义交给模型。
2. Needle 只看到 `set_light` 的 schema，返回：

   ```json
   {"name":"set_light","arguments":{"room":"bedroom","brightness":20}}
   ```

3. `execute()` 从 `TOOLS` 注册表取出 `set_light(**arguments)` 执行。
4. 工具返回 `卧室灯已打开，亮度 20%`。

索引只负责缩小注入上下文，**不会直接执行工具**。没命中索引时，系统返回空 `function_calls`，不会把全量工具表回退给模型。

## 已有工具

| 工具 | 作用 |
| --- | --- |
| `set_light(room, brightness)` | 模拟灯光和亮度 |
| `set_fan(room, level)` | 模拟风扇档位 |
| `get_temperature(room)` | 模拟房间温度 |
| `get_system_time()` | Windows 系统时间 |
| `get_weather()` | 当前配置坐标的实时天气 |
| `list_tools()` | 输出英文 `name / description` 工具表 |

天气调用 Open-Meteo；位置由 [settings/environment.json](settings/environment.json) 决定，也可在网页右上角齿轮中修改。城市字段用于显示，经纬度才是实际查询依据。

## Needle 模型与运行文件

当前仓库**不带模型文件**。`agent/needle.py` 创建的是 `needle.Needle(..., generation=3)`，没有传入 `weights` 路径，因此 `cactus-needle==3.0.1` 自动使用用户缓存：

```text
C:\Users\<用户名>\.cache\cactus-needle\v3\3.0.1\libneedle.dll
C:\Users\<用户名>\.cache\cactus-needle\v3\3.0.1\needle3.cact
```

在当前电脑上，`needle3.cact` 约为 35 MB。首次缺少运行库或权重时，Needle 会下载它们，因此第一次启动需要网络；之后可从缓存运行。

`models/` 目前只有占位文件，尚未接入。以后若要把权重随项目或设备一起带走，应把 `.cact` 放进 `models/`，并在 `agent/needle.py` 创建 `Needle` 时显式传入 `weights=".../models/needle3.cact"`；引擎 DLL 仍可继续使用缓存，或通过 `NEEDLE3_LIB_PATH` 指向设备上的 DLL。

`.venv/`、缓存和 `models/*.cact` 都被 Git 忽略，不会被提交到仓库。

## 增加一个工具

1. 在 `agent/tools/` 选合适模块新增 Python 函数，返回 `ToolResult`。
2. 在 `agent/tools/__init__.py` 的 `TOOLS` 注册函数，并补上对应 schema。
3. 在 `agent/tools/tool_index.json` 为同名工具补中英文检索词。
4. 通过网页提交一条明确英文指令，确认 JSON、执行结果都正确。

小模型的 schema 与演示指令目前以英文为主。中文检索词能让索引选择正确候选工具，但不能替代模型本身的中文理解能力。

每次成功调用底部会显示 `耗时 · tok/s`，例如 `0.18s · 557 tok/s`。耗时覆盖模型筛选、Needle 推理与工具执行；`tok/s` 使用 Needle 返回的生成速度。

## 当前范围

- 纯本地 WebUI：对话、调用结果、新建对话、位置设置。
- 模拟设备动作、系统时间、在线天气。
- 不包含真实 MQTT/ESP32/树莓派控制、账号、数据库或多对话持久化。
