"""Write validated locators into the requirement POM. Failures stay in bindings/."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from framework.pom.loader import LocatorDef


def locator_to_dict(loc: LocatorDef) -> dict[str, Any]:
    data: dict[str, Any] = {"by": loc.by, "value": loc.value}
    if loc.name is not None:
        data["name"] = loc.name
    if loc.exact is not None:
        data["exact"] = loc.exact
    return data


def load_existing_elements(pom_path: Path) -> dict[str, Any]:
    if not pom_path.is_file():
        return {"page": None, "url": None, "elements": {}}
    with pom_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        return {"page": None, "url": None, "elements": {}}
    elements = raw.get("elements") or {}
    if not isinstance(elements, dict):
        elements = {}
    return {
        "page": raw.get("page"),
        "url": raw.get("url"),
        "elements": dict(elements),
    }


def write_pom(
    pom_path: Path,
    *,
    elements: dict[str, LocatorDef],
    page: str | None,
    url: str | None,
    keep_existing: bool = True,
) -> None:
    current = load_existing_elements(pom_path) if keep_existing else {
        "page": None,
        "url": None,
        "elements": {},
    }
    merged = dict(current["elements"])
    for name, loc in elements.items():
        merged[name] = locator_to_dict(loc)
    payload: dict[str, Any] = {}
    page_name = page or current.get("page")
    page_url = url or current.get("url")
    if page_name:
        payload["page"] = page_name
    if page_url:
        payload["url"] = page_url
    payload["elements"] = merged
    pom_path.parent.mkdir(parents=True, exist_ok=True)
    with pom_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)


def write_bindings(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
