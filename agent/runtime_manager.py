from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
from threading import Lock, Thread
from time import sleep, time
from typing import Any
from urllib.request import Request, urlopen
import zipfile


ROOT = Path(__file__).parent.parent
RUNTIME_MANIFEST = ROOT / "runtime" / "manifest.json"
MODELS_DIR = ROOT / "models"
CATALOG_PATH = MODELS_DIR / "catalog.json"


class RuntimeManager:
    """Owns downloaded llama-server files and the local Qwen server process."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._server_model = ""
        self._download: dict[str, Any] = {"state": "idle"}

    def models(self, active_model: str, selected_id: str) -> dict[str, Any]:
        return {
            "active_model": active_model,
            "selected_id": selected_id,
            "runtime_ready": self.runtime_ready(),
            "download": dict(self._download),
            "models": [
                {"id": item["id"], "name": item["name"], "installed": self.model_path(item).is_file(), "downloading": self._download.get("model_id") == item["id"] and self._download.get("state") == "downloading"}
                for item in self.catalog()
            ],
        }

    def catalog(self) -> list[dict[str, Any]]:
        return list(json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["models"])

    def model(self, model_id: str) -> dict[str, Any]:
        for item in self.catalog():
            if item["id"] == model_id:
                return item
        raise ValueError("未知 Qwen 模型。")

    def model_path(self, item: dict[str, Any]) -> Path:
        return MODELS_DIR / item["filename"]

    def runtime_ready(self) -> bool:
        try:
            return self.binary_path().is_file()
        except RuntimeError:
            return False

    def start_download(self, model_id: str, include_runtime: bool) -> None:
        with self._lock:
            if self._download.get("state") == "downloading":
                raise RuntimeError("已有下载正在进行。")
            item = self.model(model_id)
            installed = self.model_path(item).is_file()
            if installed and self.runtime_ready():
                raise RuntimeError("该模型已安装。")
            if not self.runtime_ready() and not include_runtime:
                raise RuntimeError("使用 Qwen 需要先下载 llama-server。")
            self._download = {"state": "downloading", "model_id": model_id, "received": 0, "total": item["size"], "message": "准备下载"}
            Thread(target=self._download_worker, args=(item, include_runtime, installed), daemon=True, name="qwen-download").start()

    def ensure_server(self, model_id: str) -> str:
        item = self.model(model_id)
        model_path = self.model_path(item)
        if not model_path.is_file():
            raise RuntimeError("Qwen 模型未安装，请在设置的下载页下载。")
        binary = self.binary_path()
        with self._lock:
            if self._process is not None and self._process.poll() is None and self._server_model == model_id:
                return self._server_url()
            self._stop_locked()
            command = [str(binary), "-m", str(model_path), "-c", str(item.get("context_size", 4096)), "--host", "127.0.0.1", "--port", "8080", "--no-webui"]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            self._server_model = model_id
        for _ in range(80):
            if self._process is None or self._process.poll() is not None:
                raise RuntimeError("llama-server 启动失败。")
            if self._healthy():
                return self._server_url()
            sleep(0.1)
        self.stop()
        raise RuntimeError("llama-server 启动超时。")

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def binary_path(self) -> Path:
        key = self.platform_key()
        try:
            entry = self.runtime_manifest()["platforms"][key]
        except KeyError as error:
            raise RuntimeError("当前系统暂不支持自动安装 llama-server。") from error
        return ROOT / "runtime" / "bin" / key / entry["binary"]

    def platform_key(self) -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        arch = "arm64" if machine in {"arm64", "aarch64"} else "x64" if machine in {"amd64", "x86_64"} else "unknown"
        return f"{system}-{arch}"

    def runtime_manifest(self) -> dict[str, Any]:
        return json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))

    def _download_worker(self, item: dict[str, Any], include_runtime: bool, installed: bool) -> None:
        try:
            if include_runtime and not self.runtime_ready():
                self._set_download(message="正在准备 llama-server")
                self._install_runtime()
            if not installed:
                self._set_download(message="正在下载模型", received=0, total=item["size"])
                self._download_to(self.model_path(item), item["url"], item["sha256"], item["size"])
            self._set_download(state="complete", message="下载完成", received=item["size"])
        except Exception as error:
            self._set_download(state="error", message=str(error))

    def _install_runtime(self) -> None:
        key = self.platform_key()
        try:
            entry = self.runtime_manifest()["platforms"][key]
        except KeyError as error:
            raise RuntimeError("当前系统暂不支持自动安装 llama-server。") from error
        target = self.binary_path().parent
        archive = target.parent / f"{key}.{entry['archive']}"
        archive.parent.mkdir(parents=True, exist_ok=True)
        self._download_to(archive, entry["url"], entry["sha256"], None)
        unpack = target.parent / f".{key}-unpack"
        shutil.rmtree(unpack, ignore_errors=True)
        unpack.mkdir(parents=True)
        if entry["archive"] == "zip":
            with zipfile.ZipFile(archive) as file:
                self._safe_extract_zip(file, unpack)
        else:
            with tarfile.open(archive) as file:
                self._safe_extract_tar(file, unpack)
        binary = next(unpack.rglob(entry["binary"]), None)
        if binary is None:
            raise RuntimeError("下载的 llama-server 包不完整。")
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(binary.parent, target)
        if os.name != "nt":
            self.binary_path().chmod(0o755)
        archive.unlink(missing_ok=True)
        shutil.rmtree(unpack, ignore_errors=True)

    def _download_to(self, destination: Path, url: str, expected_sha: str, total: int | None) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        received = partial.stat().st_size if partial.is_file() else 0
        headers = {"User-Agent": "ai-control-box"}
        if received:
            headers["Range"] = f"bytes={received}-"
        request = Request(url, headers=headers)
        with urlopen(request, timeout=30) as response:
            if received and response.status != 206:
                partial.unlink(missing_ok=True)
                received = 0
            mode = "ab" if received else "wb"
            with partial.open(mode) as stream:
                while block := response.read(1024 * 1024):
                    stream.write(block)
                    received += len(block)
                    if total:
                        self._set_download(received=received, total=total)
        if total is not None and received != total:
            raise RuntimeError("模型下载不完整，请重试。")
        if self._sha256(partial) != expected_sha:
            partial.unlink(missing_ok=True)
            raise RuntimeError("下载校验失败，请重试。")
        partial.replace(destination)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _safe_extract_zip(file: zipfile.ZipFile, target: Path) -> None:
        for item in file.infolist():
            path = (target / item.filename).resolve()
            if not path.is_relative_to(target.resolve()):
                raise RuntimeError("运行时压缩包包含无效路径。")
        file.extractall(target)

    @staticmethod
    def _safe_extract_tar(file: tarfile.TarFile, target: Path) -> None:
        for item in file.getmembers():
            path = (target / item.name).resolve()
            if not path.is_relative_to(target.resolve()):
                raise RuntimeError("运行时压缩包包含无效路径。")
        file.extractall(target, filter="data")

    def _set_download(self, **changes: Any) -> None:
        with self._lock:
            self._download.update(changes)

    def _server_url(self) -> str:
        return "http://127.0.0.1:8080"

    def _healthy(self) -> bool:
        try:
            with urlopen(self._server_url() + "/health", timeout=0.5) as response:
                return response.status == 200
        except OSError:
            return False

    def _stop_locked(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None
        self._server_model = ""
