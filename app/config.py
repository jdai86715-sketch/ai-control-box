from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_backend: str = "llama_cpp"
    llama_cpp_url: str = "http://127.0.0.1:8080"
    llama_cpp_model: str = "local-model"
    allowed_apps: str = "记事本=notepad.exe,计算器=calc.exe"
    safe_directories: str = str(Path.home() / "Desktop")
    mqtt_broker_host: str = "127.0.0.1"
    mqtt_broker_port: int = 1883
    mqtt_topic_prefix: str = "ai-box"
    mqtt_devices: str = "客厅灯=living-room-light"

    @property
    def app_map(self) -> dict[str, str]:
        return self._parse_map(self.allowed_apps, ",")

    @property
    def device_map(self) -> dict[str, str]:
        return self._parse_map(self.mqtt_devices, ",")

    @property
    def safe_paths(self) -> list[Path]:
        return [Path(item.strip()).resolve() for item in self.safe_directories.split(";") if item.strip()]

    @staticmethod
    def _parse_map(value: str, separator: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in value.split(separator):
            name, delimiter, target = item.partition("=")
            if delimiter and name.strip() and target.strip():
                result[name.strip()] = target.strip()
        return result


settings = Settings()
