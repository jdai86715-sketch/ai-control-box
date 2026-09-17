# 截图采集清单

在发布页或 README 中加入真实截图前，请先启动 llama.cpp 与控制盒服务，再从 `http://127.0.0.1:8000/docs` 采集以下画面：

1. `GET /health` 返回正常。
2. `POST /commands` 提交“现在几点”并获得低风险执行结果。
3. `POST /commands` 提交“打开记事本”并显示“等待确认”。
4. `GET /tools` 显示工具与风险等级。

保存为 `health.png`、`time-command.png`、`confirmation.png` 和 `tools.png`。发布前确认截图中没有用户名、私有文件名、局域网地址、MQTT 凭据或其他敏感信息。
