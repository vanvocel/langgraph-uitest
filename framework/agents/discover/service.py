"""Phase 5: YAML element names → validated POM locators (heuristics + optional LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from framework.agents.discover.candidates import bind_element
from framework.agents.discover.collect import (
    collect_elements,
    collect_urls,
    load_requirement_cases,
    needs_login,
)
from framework.agents.discover.llm_candidates import ask_locator_candidates
from framework.agents.discover.snapshot import snapshot_text
from framework.agents.discover.write_pom import load_existing_elements, write_bindings, write_pom
from framework.bootstrap.login import ensure_logged_in, storage_state_for
from framework.browser.session import start_playwright
from framework.llm.profiles import LlmProfile, resolve_profile
from framework.paths import init_requirement, req_dir
from framework.pom.loader import LocatorDef
from framework.schema.case import ActionName, Step
from framework.tools.actions import ToolContext, tool_open


def _open_url(page: Page, url: str, fixture_dir: Path | None, base_url: str | None) -> None:
    ctx = ToolContext(page, elements={}, base_url=base_url, fixture_dir=fixture_dir)
    tool_open(ctx, Step(action=ActionName.open, url=url))


def _maybe_reveal(page: Page, name: str, loc: LocatorDef) -> None:
    """Reveal filters/dialogs. Do NOT auto-click every tab — that hides other elements."""
    if name in {"展开筛选"}:
        try:
            page.get_by_text("展开筛选", exact=True).first.click(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:  # noqa: BLE001
            return
    if name in {"批量领取"}:
        try:
            resolve = page.get_by_text("批量领取", exact=True)
            if resolve.count() and resolve.first.is_visible():
                resolve.first.click(timeout=3000)
                page.wait_for_timeout(500)
        except Exception:  # noqa: BLE001
            return


def _enter_primary_tab(page: Page, pending: list[str]) -> None:
    """Enter the main working tab before binding action buttons."""
    preferred = [
        "清洗评分规则",
        "人工待清洗",
        "AI 外呼待清洗",
        "清洗记录",
        "已清洗客资",
    ]
    pending_set = set(pending)
    # Map POM name → visible tab label
    aliases = {"AI外呼待清洗": "AI 外呼待清洗"}
    ordered: list[str] = []
    for label in preferred:
        pom_name = next((k for k, v in aliases.items() if v == label), label)
        if label in pending_set or pom_name in pending_set or label in {
            "人工待清洗",
            "清洗评分规则",
        }:
            ordered.append(label)
    for label in ordered:
        try:
            tab = page.get_by_role("tab", name=label)
            if tab.count() and tab.first.is_visible():
                tab.first.click(timeout=3000)
                page.wait_for_timeout(500)
                return
        except Exception:  # noqa: BLE001
            continue


def _try_open_batch_dialog(page: Page) -> None:
    try:
        btn = page.get_by_text("批量领取", exact=True)
        if btn.count() and btn.first.is_visible():
            btn.first.click(timeout=3000)
            page.wait_for_timeout(600)
    except Exception:  # noqa: BLE001
        return


def _bind_pending(
    page: Page,
    pending: list[str],
    *,
    extras: dict[str, list[LocatorDef]] | None = None,
) -> tuple[dict[str, LocatorDef], list[str], dict[str, float]]:
    bound: dict[str, LocatorDef] = {}
    scores: dict[str, float] = {}
    left = list(pending)
    for name in list(left):
        if name not in left:
            continue
        hit = bind_element(page, name, extra=(extras or {}).get(name))
        if hit is None:
            continue
        loc, score = hit
        bound[name] = loc
        scores[name] = score
        left.remove(name)
        _maybe_reveal(page, name, loc)
        for again in list(left):
            hit2 = bind_element(page, again, extra=(extras or {}).get(again))
            if hit2 is None:
                continue
            loc2, score2 = hit2
            bound[again] = loc2
            scores[again] = score2
            left.remove(again)
            _maybe_reveal(page, again, loc2)
    return bound, left, scores


def discover_on_page(
    page: Page,
    names: list[str],
    *,
    already: dict[str, Any],
    force: bool,
    llm_profile: LlmProfile | None = None,
) -> tuple[dict[str, LocatorDef], list[str], dict[str, float], str, str]:
    pending = [name for name in names if force or name not in already]
    _enter_primary_tab(page, pending)
    bound, still, scores = _bind_pending(page, pending)
    backend = "heuristic"
    llm_error = ""

    dialog_names = {"批量领取", "弹窗", "弹窗关闭", "弹窗_继续清洗"}
    if still and dialog_names.intersection(still):
        _enter_primary_tab(page, pending)
        _try_open_batch_dialog(page)
        more, still, more_scores = _bind_pending(page, still)
        bound.update(more)
        scores.update(more_scores)

    if still and llm_profile and llm_profile.has_key:
        try:
            if dialog_names.intersection(still):
                _try_open_batch_dialog(page)
            snap = snapshot_text(page)
            llm_map = ask_locator_candidates(
                element_names=still,
                snapshot=snap,
                profile=llm_profile,
            )
            more, still, more_scores = _bind_pending(page, still, extras=llm_map)
            bound.update(more)
            scores.update(more_scores)
            backend = llm_profile.name
        except Exception as exc:  # noqa: BLE001
            llm_error = str(exc)
    return bound, still, scores, backend, llm_error


def discover_requirement(
    req_id: str,
    *,
    force: bool = False,
    page: Page | None = None,
    llm_profile: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    init_requirement(req_id)
    base = req_dir(req_id)
    cases = load_requirement_cases(base / "yaml")
    if not cases:
        raise FileNotFoundError(f"no YAML cases under {base / 'yaml'}")

    names = collect_elements(cases)
    urls = collect_urls(cases)
    pom_path = base / "pom" / "elements.yaml"
    existing = load_existing_elements(pom_path)
    already = {} if force else dict(existing.get("elements") or {})

    account_ref = needs_login(cases)
    fixture_dir = base / "fixtures"
    if not fixture_dir.is_dir():
        fixture_dir = None
    base_url = next((c.base_url for c in cases if c.base_url), None)

    profile: LlmProfile | None = None
    if use_llm:
        profile = resolve_profile(llm_profile or None)
        if not profile.has_key:
            profile = None

    owned_session = page is None
    playwright = browser = context = None
    if owned_session:
        state = storage_state_for(account_ref) if account_ref else None
        playwright, browser, context, page = start_playwright(storage_state=state)
    assert page is not None

    bound: dict[str, LocatorDef] = {}
    scores: dict[str, float] = {}
    still = list(names)
    backend = "heuristic"
    llm_error = ""
    try:
        if account_ref:
            ensure_logged_in(page, account_ref=account_ref)
        if not urls:
            urls = [page.url] if page.url else []
        for url in urls:
            _open_url(page, url, fixture_dir, base_url)
            page.wait_for_timeout(600)
            found, still, part_scores, backend, err = discover_on_page(
                page,
                still,
                already=already,
                force=force,
                llm_profile=profile,
            )
            bound.update(found)
            scores.update(part_scores)
            if err:
                llm_error = err
            if not still:
                break
    finally:
        if owned_session:
            if context:
                context.close()
            if browser:
                browser.close()
            if playwright:
                playwright.stop()

    skipped = [n for n in names if n in already and n not in bound]
    write_pom(
        pom_path,
        elements=bound,
        page=existing.get("page") or req_id,
        url=existing.get("url") or (urls[0] if urls else None),
        keep_existing=not force,
    )
    unbound = [n for n in names if n not in already and n not in bound]
    if force:
        unbound = [n for n in names if n not in bound]
        skipped = []
    report = {
        "req_id": req_id,
        "needed": names,
        "bound": {
            k: {"by": v.by, "value": v.value, "name": v.name, "exact": v.exact, "confidence": scores.get(k)}
            for k, v in bound.items()
        },
        "kept": skipped,
        "unbound": unbound,
        "blocked": bool(unbound),
        "backend": backend,
        "llm_profile": profile.name if profile else None,
        "llm_error": llm_error or None,
        "pom": str(pom_path),
    }
    write_bindings(base / "bindings" / "discover.yaml", report)
    return report
