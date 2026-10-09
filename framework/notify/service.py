"""Build report payload from runs/<req> and dispatch to enabled channels."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from framework.notify.base import NotifyResult
from framework.notify.models import ReportPayload
from framework.notify.registry import create_channel, known_channels
from framework.paths import project_root, req_dir


def load_notify_config() -> dict[str, Any]:
    path = project_root() / "config" / "notify.yaml"
    if not path.is_file():
        return {"enabled": False, "channels": {}}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_report_base_url(cfg: dict[str, Any] | None = None) -> str:
    """Public base URL that maps to runs/ on the server (no trailing slash)."""
    cfg = cfg if cfg is not None else load_notify_config()
    section = dict(cfg.get("report_url") or {})
    direct = str(section.get("base_url") or "").strip()
    if direct:
        return direct.rstrip("/")
    env_name = str(section.get("base_url_env") or "REPORT_BASE_URL").strip()
    return os.getenv(env_name, "").strip().rstrip("/")


def resolve_report_url(
    req_id: str,
    *,
    html_path: Path | None = None,
    cfg: dict[str, Any] | None = None,
) -> str | None:
    """Build clickable Allure URL for deployed/static hosting."""
    cfg = cfg if cfg is not None else load_notify_config()
    base_url = resolve_report_base_url(cfg)
    if not base_url:
        return None
    section = dict(cfg.get("report_url") or {})
    html = html_path or _find_html(req_dir(req_id))
    if html is None:
        return None
    # Prefer configured template; otherwise derive from file location under runs/.
    template = str(section.get("html_path_template") or "").strip()
    if template:
        rel = template.format(req_id=req_id).lstrip("/")
    else:
        try:
            rel = html.relative_to(req_dir(req_id).parent).as_posix()
        except ValueError:
            rel = f"{req_id}/{html.name}"
    return f"{base_url}/{rel}"


def _find_excel(base: Path, req_id: str) -> Path | None:
    summary = base / "excel_backfill_summary.json"
    if summary.is_file():
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
            p = Path(str(data.get("excel") or ""))
            if p.is_file():
                return p
        except (json.JSONDecodeError, OSError):
            pass
    preferred = base / f"{req_id}_结果回填.xlsx"
    if preferred.is_file():
        return preferred
    hits = sorted(base.glob("*结果回填*.xlsx")) + sorted(base.glob("*backfill*.xlsx"))
    return hits[0] if hits else None


def _find_html(base: Path) -> Path | None:
    single = base / "allure-report.html"
    if single.is_file():
        return single
    index = base / "allure-report" / "index.html"
    if index.is_file():
        return index
    return None


def _failed_cases_from_logs(base: Path) -> list[str]:
    logs = base / "logs"
    if not logs.is_dir():
        return []
    failed: list[str] = []
    for path in sorted(logs.glob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if '"event": "case_fail"' in text or '"event":"case_fail"' in text:
            failed.append(path.stem)
    return failed


def _stats_from_summary(base: Path) -> dict[str, int]:
    summary = base / "excel_backfill_summary.json"
    if not summary.is_file():
        return {}
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    stats = data.get("stats") or {}
    return {
        "passed": int(stats.get("通过") or stats.get("passed") or 0),
        "failed": int(stats.get("失败") or stats.get("failed") or 0),
        "blocked": int(stats.get("Block") or stats.get("blocked") or 0),
    }


def build_report_payload(
    req_id: str,
    *,
    exit_code: int | None = None,
    title: str | None = None,
) -> ReportPayload:
    base = req_dir(req_id)
    stats = _stats_from_summary(base)
    html = _find_html(base)
    cfg = load_notify_config()
    report_url = resolve_report_url(req_id, html_path=html, cfg=cfg)
    if report_url:
        (base / "report_url.txt").write_text(report_url + "\n", encoding="utf-8")
    return ReportPayload(
        req_id=req_id,
        title=title or f"{req_id} UI 自动化结果",
        passed=stats.get("passed", 0),
        failed=stats.get("failed", 0),
        blocked=stats.get("blocked", 0),
        exit_code=exit_code,
        excel_path=_find_excel(base, req_id),
        html_path=html,
        report_url=report_url,
        summary_path=(base / "excel_backfill_summary.json")
        if (base / "excel_backfill_summary.json").is_file()
        else None,
        failed_cases=_failed_cases_from_logs(base),
    )


def notify_report(
    req_id: str,
    *,
    exit_code: int | None = None,
    channels: list[str] | None = None,
    force: bool = False,
) -> list[NotifyResult]:
    """Send report via enabled channels. Returns per-channel results."""
    cfg = load_notify_config()
    if not force and not cfg.get("enabled", False):
        return [
            NotifyResult(
                channel="*",
                ok=False,
                message="notify disabled (config/notify.yaml enabled: false)",
            )
        ]

    only_fail = bool(cfg.get("only_on_failure", False))
    payload = build_report_payload(req_id, exit_code=exit_code)
    if only_fail and not payload.has_failure and not force:
        return [
            NotifyResult(
                channel="*",
                ok=True,
                message="skipped: only_on_failure=true and no failures",
            )
        ]

    channel_cfgs = dict(cfg.get("channels") or {})
    names = channels or [
        name
        for name, ch in channel_cfgs.items()
        if isinstance(ch, dict) and ch.get("enabled")
    ]
    if not names:
        return [
            NotifyResult(
                channel="*",
                ok=False,
                message=f"no enabled channels; known={known_channels()}",
            )
        ]

    results: list[NotifyResult] = []
    for name in names:
        ch_cfg = dict(channel_cfgs.get(name) or {})
        try:
            channel = create_channel(name, ch_cfg)
        except ValueError as exc:
            results.append(NotifyResult(channel=name, ok=False, message=str(exc)))
            continue
        results.append(channel.send(payload))
    return results


def should_notify_after_run() -> bool:
    cfg = load_notify_config()
    return bool(cfg.get("enabled"))
