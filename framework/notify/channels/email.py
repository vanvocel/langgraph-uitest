"""Email channel placeholder — enable when SMTP credentials are ready."""

from __future__ import annotations

from typing import Any

from framework.notify.base import NotifyChannel, NotifyResult
from framework.notify.models import ReportPayload


class EmailChannel(NotifyChannel):
    name = "email"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)

    def send(self, payload: ReportPayload) -> NotifyResult:
        return NotifyResult(
            channel=self.name,
            ok=False,
            message="email channel not implemented yet; set channels.email.enabled=false",
        )
