# 最小 AI 控制盒设计

## 目标

在 Windows 上跑通从自然语言工具调用到 Python 模拟设备动作的完整链路。浏览器页面仅提供对话输入、调用/结果输出和新建对话。

## 目录

```text
ai-control-box/
├─ main.py
├─ settings/
│  └─ environment.json      # 当前环境位置等可修改信息
├─ agent/
│  ├─ models.py
│  ├─ config.py
│  ├─ tools/
│  │  ├─ device.py
│  │  ├─ environment.py
│  │  ├─ tool_index.json
│  │  └─ __init__.py         # 注册表、schema、筛选和分发入口
│  ├─ web.py
│  ├─ needle.py        # Needle 的唯一模型适配边界
│  └─ static/          # 唯一 Web 页面所需的 HTML、JS、CSS
├─ models/              # 未来手动放置本地权重，忽略 Git
└─ TASK_STATE.md
```

`main.py` 只启动本地 Web 服务。`agent` 是所有运行代码的唯一业务目录，避免分散为多个顶层模块。
Needle 通过固定版本的 `cactus-needle` 依赖提供；不复制其训练、微调、示例环境或 Playground 代码。

## 调用链

```text
WebUI 输入
→ web.py
→ tools/tool_index.json 筛出候选工具
→ models.py 只注入候选 schema
→ function_calls JSON
→ tools.py
→ WebUI 显示调用和中文结果
```

模型返回的标准调用为：

```json
{"name":"set_light","arguments":{"room":"卧室","brightness":20}}
```

工具返回结构化结果，例如：

```json
{"ok":true,"event":"light.set","data":{"room":"卧室","brightness":20},"message":"卧室灯已打开，亮度 20%"}
```

中文结果由工具逻辑的固定模板产生，不要求 Needle 生成自然语言回复。

工具索引以本地 JSON 保存；每个已注册工具拥有英文和中文检索词。索引只缩小 Needle 的可见 schema，不能直接触发动作；模型仍必须输出名称与参数，`tools.py` 再按已注册名称执行。未命中索引时返回空调用，不把全量工具表回退注入模型。

## 首批行为

- `set_light(room, brightness)`：返回模拟灯光状态。
- `set_fan(room, level)`：返回模拟风扇状态。
- `get_temperature(room)`：返回模拟温度读取结果。
- `get_system_time()`：读取 Windows 系统时间。
- `get_weather()`：读取 `settings/environment.json` 的经纬度，通过 Open-Meteo 返回当前天气。

首次实现提供可重复的本地演示调用；Needle 集成后替换模型输出来源，而不改 Web、工具或 Tk 链路。

## 页面范围

- 单一页面。
- 一条输入框与图标发送按钮。
- 对话区域显示原始输入、工具调用 JSON 和中文结果。
- 右上角图标提供新建对话与设置；设置浮层修改城市、纬度和经度。
- 页面为纯黑、无对话卡片背景的极简布局。

## 不做的内容

- 不做账号、数据库、跨浏览器历史、登录、配置面板。
- 不做真实 Windows 自动化、MQTT、ESP32 或树莓派连接。
- 不做风险确认、白名单、关键词规则路由。
- 不增加额外页面。

## 验收

1. 启动后自动打开本地页面。
2. 提交演示指令后，页面显示调用 JSON 与中文结果。
3. 新建对话后，页面记录清空且可继续提交。
