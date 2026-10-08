"""Build Allure HTML from pytest --alluredir results."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# allure-pytest 2.16+ writes titlePath; Allure CLI 2.13.x Jackson rejects it
# and then generates an empty report.
_STRIP_KEYS = ("titlePath",)


def sanitize_allure_results(results_dir: Path) -> int:
    """Remove fields that old Allure CLI cannot deserialize. Returns files changed."""
    changed = 0
    for path in results_dir.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _strip_unknown(raw):
            path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            changed += 1
    return changed


def _strip_unknown(node: object) -> bool:
    changed = False
    if isinstance(node, dict):
        for key in _STRIP_KEYS:
            if key in node:
                node.pop(key, None)
                changed = True
        for value in node.values():
            if _strip_unknown(value):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if _strip_unknown(item):
                changed = True
    return changed


def _summary_total(report_dir: Path) -> int:
    summary = report_dir / "widgets" / "summary.json"
    if not summary.is_file():
        return 0
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    stats = data.get("statistic") or {}
    return int(stats.get("total") or 0)


def promote_step_screenshots(results_dir: Path) -> int:
    """Copy assertion PNG attachments from steps onto the test case so Overview shows them."""
    changed = 0
    for path in results_dir.glob("*-result.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found: list[dict] = []
        _collect_pngs(raw.get("steps") or [], found)
        if not found:
            continue
        existing = raw.setdefault("attachments", [])
        have = {(a.get("source"), a.get("name")) for a in existing if isinstance(a, dict)}
        added = False
        for att in found:
            key = (att.get("source"), att.get("name"))
            if key in have:
                continue
            existing.append(dict(att))
            have.add(key)
            added = True
        if added:
            path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            changed += 1
    return changed


def _collect_pngs(steps: list, out: list[dict]) -> None:
    for step in steps:
        if not isinstance(step, dict):
            continue
        for att in step.get("attachments") or []:
            if isinstance(att, dict) and att.get("type") == "image/png":
                out.append(att)
        _collect_pngs(step.get("steps") or [], out)


def _allure_generate_cmds(results_dir: Path, report_dir: Path, *, single_file: bool) -> list[list[str]]:
    extra = ["--single-file"] if single_file else []
    cmds: list[list[str]] = []
    npx = shutil.which("npx")
    if npx:
        cmds.append(
            [
                npx,
                "--yes",
                "allure-commandline@2.34.1",
                "generate",
                str(results_dir),
                "-o",
                str(report_dir),
                "--clean",
                *extra,
            ]
        )
    exe = shutil.which("allure")
    if exe:
        cmds.append([exe, "generate", str(results_dir), "-o", str(report_dir), "--clean", *extra])
    return cmds


def _is_single_file_html(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size < 20_000:
        return False
    head = path.read_bytes()[:4096].decode("utf-8", errors="ignore").lower()
    return "allure" in head


def generate_allure_report(results_dir: Path, report_dir: Path | None = None) -> Path | None:
    """Return a double-clickable HTML path when possible, else the report directory."""
    results_dir = Path(results_dir)
    report_dir = Path(report_dir) if report_dir else results_dir.parent / "allure-report"
    standalone = report_dir.parent / "allure-report.html"
    if not results_dir.is_dir() or not any(results_dir.iterdir()):
        return None

    sanitize_allure_results(results_dir)
    promote_step_screenshots(results_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    for cmd in _allure_generate_cmds(results_dir, report_dir, single_file=True):
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            continue
        index = report_dir / "index.html"
        if _is_single_file_html(index):
            shutil.copy2(index, standalone)
            return standalone

    for cmd in _allure_generate_cmds(results_dir, report_dir, single_file=False):
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            continue
        if _summary_total(report_dir) > 0:
            return report_dir
    if (report_dir / "index.html").is_file() and _summary_total(report_dir) > 0:
        return report_dir
    return None
