"""Collect unique pages and semantic element names from requirement YAML."""

from __future__ import annotations

from pathlib import Path

from framework.schema.case import ActionName, UiCase
from framework.schema.loader import list_case_files, load_case


def load_requirement_cases(yaml_dir: Path) -> list[UiCase]:
    return [load_case(path) for path in list_case_files(yaml_dir)]


def collect_urls(cases: list[UiCase]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for case in cases:
        for step in case.steps:
            if step.action != ActionName.open:
                continue
            url = (step.url or step.value or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def collect_elements(cases: list[UiCase]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for case in cases:
        for step in case.steps:
            name = (step.element or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def needs_login(cases: list[UiCase]) -> str | None:
    for case in cases:
        for pre in case.preconditions:
            if pre.auth == "logged_in":
                return pre.account_ref or "default_tester"
    return None
