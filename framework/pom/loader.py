"""POM element map loader (per-requirement)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from framework.runner.errors import FailureCode, StepError


class LocatorDef(BaseModel):
    by: Literal["css", "xpath", "role", "text", "testid", "id", "placeholder", "label"]
    value: str
    name: str | None = None  # for role
    exact: bool | None = None


class PomMap(BaseModel):
    page: str | None = None
    url: str | None = None
    elements: dict[str, LocatorDef] = Field(default_factory=dict)


def load_pom(pom_dir: Path) -> PomMap:
    """Merge elements.yaml / *.yaml under pom/ into one map."""
    if not pom_dir.is_dir():
        raise StepError(FailureCode.BIND_ERROR, f"pom directory missing: {pom_dir}")

    merged: dict[str, Any] = {"elements": {}}
    files = sorted(
        p for p in pom_dir.iterdir() if p.suffix in {".yaml", ".yml"} and p.is_file()
    )
    if not files:
        raise StepError(FailureCode.BIND_ERROR, f"no POM yaml under {pom_dir}")

    for path in files:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if not isinstance(raw, dict):
            continue
        if "page" in raw and merged.get("page") is None:
            merged["page"] = raw["page"]
        if "url" in raw and merged.get("url") is None:
            merged["url"] = raw["url"]
        elements = raw.get("elements") or {}
        if isinstance(elements, dict):
            merged["elements"].update(elements)

    return PomMap.model_validate(merged)


def resolve_locator(page, locator: LocatorDef):
    """Return a Playwright Locator from LocatorDef."""
    by = locator.by
    value = locator.value
    if by == "css":
        return page.locator(value)
    if by == "xpath":
        return page.locator(f"xpath={value}")
    if by == "id":
        return page.locator(f"#{value}" if not value.startswith("#") else value)
    if by == "testid":
        return page.get_by_test_id(value)
    if by == "text":
        return page.get_by_text(value, exact=bool(locator.exact))
    if by == "placeholder":
        return page.get_by_placeholder(value, exact=bool(locator.exact) if locator.exact is not None else False)
    if by == "label":
        return page.get_by_label(value, exact=bool(locator.exact) if locator.exact is not None else False)
    if by == "role":
        kwargs = {}
        if locator.name is not None:
            kwargs["name"] = locator.name
        if locator.exact is not None:
            kwargs["exact"] = locator.exact
        return page.get_by_role(value, **kwargs)
    raise StepError(FailureCode.BIND_ERROR, f"unsupported locator by={by}")
