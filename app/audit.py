from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_PATH = Path("data/audit.log")


def write_audit(event: str, details: dict[str, Any]) -> None:
    AUDIT_PATH.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}
    with AUDIT_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")
