"""Shared report payload for all notify channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReportPayload:
    """Channel-agnostic test report package."""

    req_id: str
    title: str
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    exit_code: int | None = None
    excel_path: Path | None = None
    html_path: Path | None = None
    report_url: str | None = None
    summary_path: Path | None = None
    failed_cases: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def total_ui(self) -> int:
        return self.passed + self.failed

    @property
    def has_failure(self) -> bool:
        return self.failed > 0 or (self.exit_code not in (None, 0))

    def summary_text(self) -> str:
        lines = [
            f"【UI 测试报告】{self.title}",
            f"需求：{self.req_id}",
            f"通过：{self.passed}  失败：{self.failed}  Block：{self.blocked}",
        ]
        if self.exit_code is not None:
            lines.append(f"进程退出码：{self.exit_code}")
        if self.failed_cases:
            preview = "、".join(self.failed_cases[:15])
            more = f" 等{len(self.failed_cases)}条" if len(self.failed_cases) > 15 else ""
            lines.append(f"失败用例：{preview}{more}")
        if self.report_url:
            lines.append(f"报告链接：{self.report_url}")
        elif self.html_path:
            lines.append(f"HTML：{self.html_path.name}")
        if self.excel_path:
            lines.append(f"Excel：{self.excel_path.name}")
        return "\n".join(lines)

    def attachment_paths(self, *, excel: bool = True, html: bool = True) -> list[Path]:
        out: list[Path] = []
        if excel and self.excel_path and self.excel_path.is_file():
            out.append(self.excel_path)
        # Prefer URL over uploading huge HTML when report_url is set.
        if html and not self.report_url and self.html_path and self.html_path.is_file():
            out.append(self.html_path)
        return out
