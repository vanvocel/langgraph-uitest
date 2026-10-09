"""企业微信 channel placeholder."""

from __future__ import annotations

from typing import Any

from framework.notify.base import NotifyChannel, NotifyResult
from framework.notify.models import ReportPayload


class WecomChannel(NotifyChannel):
    name = "wecom"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)

    def send(self, payload: ReportPayload) -> NotifyResult:
        return NotifyResult(
            channel=self.name,
            ok=False,
            message="wecom channel not implemented yet; set channels.wecom.enabled=false",
        )
