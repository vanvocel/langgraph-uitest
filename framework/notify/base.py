"""Notify channel contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from framework.notify.models import ReportPayload


@dataclass
class NotifyResult:
    channel: str
    ok: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class NotifyChannel(ABC):
    """One delivery backend (Feishu / Email / WeCom / ...)."""

    name: str = "base"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    @abstractmethod
    def send(self, payload: ReportPayload) -> NotifyResult:
        """Deliver the report. Must not raise for expected config gaps — return ok=False."""
