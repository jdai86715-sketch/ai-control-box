from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import perf_counter
from typing import Any
import webbrowser

from .config import get_settings, save_settings, get_model_settings, save_model_settings
from .models import ModelRouter
from .runtime_manager import RuntimeManager
from .tools import constraint_error, execute, get_registry, input_constraint_error, install_plugin_files, tool_schemas


STATIC = Path(__file__).with_name("static")


class ControlBox:
    def __init__(self) -> None:
        self._runtime = RuntimeManager()
        self._model = ModelRouter(self._runtime)

    def chat(self, text: str) -> dict[str, Any]:
        started = perf_counter()
        self._model.reset()
        model_kind = get_model_settings()["active_model"]
        route = "control"
        if model_kind == "qwen":
            route = self._model.route(text)
        response = (
            {"function_calls": [], "reasoning": "Qwen chat route", "decode_tps": None}
            if route == "chat"
            else self._model.plan(text)
        )
        reply = str(response.get("reply") or "")
        if route == "chat":
            reply = self._model.answer(text)
        calls: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        feedback_steps = 0
        first_decode_tps = response.get("decode_tps")
        for step in range(3):
            step_calls = _unique_calls(response.get("function_calls") or [])
            trace.append(
                {
                    "phase": "Input" if step == 0 else "Tool-result feedback",
                    "reasoning": response.get("reasoning"),
                    "has_calls": bool(step_calls),
                }
            )
            if not step_calls:
                if not calls:
                    error = constraint_error(response)
                    if error is not None:
                        results.append(error)
                    elif model_kind == "qwen" and route == "control":
                        reply = self._model.answer(text)
                break
            step_results = [input_constraint_error(call, text) or execute(call) for call in step_calls]
            calls.extend(step_calls)
            results.extend(step_results)
            response = self._model.feed_results(step_results)
            feedback_steps += 1
        return {
            "model": response,
            "reply": reply,
            "calls": calls,
            "results": results,
            "stats": {"elapsed_seconds": perf_counter() - started, "decode_tps": first_decode_tps},
            "trace": trace,
            "context": {
                "declared_tool_schemas": len(tool_schemas()),
                "retrieval_limit": "all" if model_kind == "qwen" else 5,
                "model_kind": model_kind,
                "feedback_steps": feedback_steps,
            },
        }

    def reset(self) -> dict[str, bool]:
        self._model.reset()
        return {"ok": True}

    def tools(self) -> dict[str, Any]:
        return get_registry().settings_tools()

    def model_settings(self) -> dict[str, Any]:
        return get_model_settings()

    def models(self) -> dict[str, Any]:
        settings = get_model_settings()
        return self._runtime.models(settings["active_model"], settings["qwen"]["model_id"])

    def download_model(self, model_id: str, include_runtime: bool) -> dict[str, Any]:
        self._runtime.start_download(model_id, include_runtime)
        return self.models()

    def save_model_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        value = save_model_settings(data)
        self._model.reset()
        return value

    def install_plugin(self, files: list[dict[str, Any]]) -> dict[str, Any]:
        result = install_plugin_files(files)
        self._model.reset()
        return result

    def close(self) -> None:
        self._runtime.stop()


def _unique_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A small model may repeat one exact call; execute it once per planning step."""
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for call in calls:
        if not isinstance(call, dict):
            continue
        key = json.dumps({"name": call.get("name"), "arguments": call.get("arguments")}, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(call)
    return unique


def handler_for(box: ControlBox) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            try:
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/api/chat":
                    text = str(body.get("text", "")).strip()
                    if not text:
                        raise ValueError("请输入一句指令。")
                    self._json(200, box.chat(text))
                elif self.path == "/api/reset":
                    self._json(200, box.reset())
                elif self.path == "/api/settings":
                    self._json(200, save_settings(body))
                elif self.path == "/api/model-settings":
                    self._json(200, box.save_model_settings(body))
                elif self.path == "/api/models/download":
                    self._json(200, box.download_model(str(body.get("id", "")), bool(body.get("include_runtime"))))
                elif self.path == "/api/plugins/install":
                    self._json(200, box.install_plugin(list(body.get("files") or [])))
                else:
                    self._json(404, {"error": "not found"})
            except Exception as error:
                self._json(400, {"error": str(error)})

        def do_GET(self) -> None:
            if self.path == "/api/settings":
                self._json(200, get_settings())
                return
            if self.path == "/api/tools":
                self._json(200, box.tools())
                return
            if self.path == "/api/model-settings":
                self._json(200, box.model_settings())
                return
            if self.path == "/api/models":
                self._json(200, box.models())
                return
            name = "index.html" if self.path in {"/", "/index.html"} else self.path.lstrip("/")
            target = (STATIC / name).resolve()
            if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            content_types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".png": "image/png"}
            self._send(200, target.read_bytes(), content_types.get(target.suffix, "application/octet-stream"))

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict[str, Any]) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, *_: object) -> None:
            return

    return Handler


def run() -> None:
    box = ControlBox()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(box))
    url = f"http://127.0.0.1:{server.server_port}/"
    webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        box.close()
