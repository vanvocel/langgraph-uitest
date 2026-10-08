"""Structured JSON-line logging for a requirement run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, log_path: Path, *, case_id: str, req_id: str) -> None:
        self.log_path = log_path
        self.case_id = case_id
        self.req_id = req_id
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")

    def write(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "req_id": self.req_id,
            "case_id": self.case_id,
            "event": event,
            **fields,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
