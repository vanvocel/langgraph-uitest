"""Just-in-time element binding on the live page during case execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from framework.agents.discover.candidates import bind_element
from framework.agents.discover.llm_candidates import ask_locator_candidates
from framework.agents.discover.snapshot import snapshot_text
from framework.agents.discover.write_pom import write_pom
from framework.llm.profiles import LlmProfile, resolve_profile
from framework.pom.loader import LocatorDef


def live_bind_element(
    page: Page,
    name: str,
    *,
    use_llm: bool = True,
    llm_profile: str | None = None,
    exclude: LocatorDef | None = None,
) -> tuple[LocatorDef, float] | None:
    """Bind one element on the current page state (heuristic, then optional LLM)."""
    hit = bind_element(page, name, exclude=exclude)
    if hit is not None:
        return hit
    if not use_llm:
        return None
    try:
        profile: LlmProfile = resolve_profile(llm_profile or None)
    except Exception:  # noqa: BLE001
        return None
    if not profile.has_key:
        return None
    try:
        snap = snapshot_text(page)
        llm_map = ask_locator_candidates(
            element_names=[name],
            snapshot=snap,
            profile=profile,
        )
        extra = llm_map.get(name) or []
        return bind_element(page, name, extra=extra, exclude=exclude)
    except Exception:  # noqa: BLE001
        return None


def persist_binding(
    pom_path: Path,
    name: str,
    loc: LocatorDef,
    *,
    page_name: str | None = None,
    url: str | None = None,
    min_confidence: float = 0.9,
    confidence: float | None = None,
) -> None:
    """Append/overwrite a single element into the requirement POM."""
    if confidence is not None and confidence < min_confidence:
        return
    write_pom(
        pom_path,
        elements={name: loc},
        page=page_name,
        url=url,
        keep_existing=True,
    )


def live_bind_report(name: str, loc: LocatorDef, score: float) -> dict[str, Any]:
    return {
        "element": name,
        "by": loc.by,
        "value": loc.value,
        "name": loc.name,
        "exact": loc.exact,
        "confidence": score,
        "source": "live_bind",
    }
