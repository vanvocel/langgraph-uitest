"""Config for Excel → NL conversion."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from framework.paths import load_settings, req_dir


_HEADER_ALIASES = {
    "case_id": ("用例ID", "用例编号", "case_id", "Case ID", "用例id"),
    "title": ("用例标题", "标题", "title", "用例名称"),
    "precondition": ("前置条件", "前置", "precondition", "预置条件"),
    "steps": ("测试步骤", "步骤", "steps", "操作步骤"),
    "expect": ("预期结果", "期望结果", "预期", "expect", "expected"),
    "note": ("测试说明", "备注", "说明", "note", "comment"),
    "module": ("模块", "module"),
    "req_no": ("钉钉需求编号", "需求编号", "需求ID", "requirement_id"),
}


@dataclass
class ExcelToNlConfig:
    header_row: int = 2
    data_start_row: int = 3
    account_ref: str = "default_tester"
    # Global defaults; prefer runs/<req>/excel_nl.yaml for page entry.
    default_page_url: str = ""
    default_tab: str = ""
    page_url: str = ""
    tab: str = ""
    sheet: str | None = None
    # Extra case_ids forced into skip buckets (optional)
    ai_outbound_ids: list[str] = field(default_factory=list)
    needs_fixture_ids: list[str] = field(default_factory=list)


def load_excel_to_nl_config(
    req_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> ExcelToNlConfig:
    raw = dict(load_settings().get("excel_to_nl") or {})
    per_req = req_dir(req_id) / "excel_nl.yaml"
    if per_req.is_file():
        with per_req.open(encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        if isinstance(local, dict):
            raw.update(local)
    if overrides:
        raw.update({k: v for k, v in overrides.items() if v is not None})
    known = {f.name for f in ExcelToNlConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    return ExcelToNlConfig(**{k: v for k, v in raw.items() if k in known})


def header_aliases() -> dict[str, tuple[str, ...]]:
    return dict(_HEADER_ALIASES)


def write_req_excel_nl_template(req_id: str) -> Path:
    """Create runs/<req>/excel_nl.yaml skeleton if missing."""
    path = req_dir(req_id) / "excel_nl.yaml"
    if path.is_file():
        return path
    path.write_text(
        (
            f"# Excel → NL options for {req_id}\n"
            "# page_url / tab are injected into every generated NL file.\n"
            "page_url: \"\"\n"
            "tab: \"\"\n"
            "# Optional hard-coded skip lists (also auto-detect from Excel text):\n"
            "# ai_outbound_ids: []\n"
            "# needs_fixture_ids: []\n"
        ),
        encoding="utf-8",
    )
    return path
