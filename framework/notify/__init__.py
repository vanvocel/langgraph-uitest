"""Multi-channel test report notification (auto after run)."""

from framework.notify.base import NotifyChannel, NotifyResult
from framework.notify.models import ReportPayload
from framework.notify.service import (
    build_report_payload,
    notify_report,
    resolve_report_url,
    should_notify_after_run,
)

__all__ = [
    "NotifyChannel",
    "NotifyResult",
    "ReportPayload",
    "build_report_payload",
    "notify_report",
    "resolve_report_url",
    "should_notify_after_run",
]
