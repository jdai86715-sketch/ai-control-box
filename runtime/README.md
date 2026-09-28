# 项目内 llama.cpp 服务

首次使用时，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File runtime\setup-qwen.ps1
```

它会从 llama.cpp 和 Qwen 的官方页面下载运行程序与模型到当前项目；这些大文件不会提交到 GitHub。随后双击 `start-llama-server.bat`，它会使用项目内的 Qwen 模型启动本地服务。

服务地址为 `http://127.0.0.1:8080`。同一台电脑上的 AI Control Box 和其他应用可连接这个地址；关闭命令窗口即可停止服务。

将整个项目文件夹复制给其他用户时，需要保留以下内容：

- `runtime/setup-qwen.ps1`
- `runtime/start-llama-server.bat`
- 或者让对方自行运行首次下载脚本。

默认只允许本机应用访问，不会暴露到局域网。
