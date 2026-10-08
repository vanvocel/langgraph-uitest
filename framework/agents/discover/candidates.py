"""Heuristic locator candidates. LLM is optional later; execution still has no LLM."""

from __future__ import annotations

from collections.abc import Iterator

from playwright.sync_api import Page

from framework.pom.loader import LocatorDef, resolve_locator

_MIN_CONFIDENCE = 0.65

_ROLE_BUTTONISH = ("button", "tab", "link", "menuitem")


def _form_control_xpath(name: str) -> str:
    return (
        f"//*[normalize-space()={_xq(name)} and not(ancestor::*[contains(@class,'el-table')]) "
        "and not(ancestor::aside) and not(ancestor::*[contains(@class,'el-menu')])]"
        "/following::*[contains(@class,'el-select__wrapper') or contains(@class,'el-select') "
        "or contains(@class,'el-input') or self::input or self::textarea][1]"
    )


def _xq(text: str) -> str:
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def iter_candidates(name: str) -> Iterator[LocatorDef]:
    if name in {"页面"}:
        yield LocatorDef(by="css", value="body")
        return
    if name in {"列表表格", "表格"}:
        yield LocatorDef(by="css", value=".el-table")
        yield LocatorDef(by="css", value="table")
        return
    if name in {"列表行"}:
        yield LocatorDef(by="css", value=".el-table__body tbody tr:not(.el-table__empty-row)")
        return
    if name in {"弹窗"}:
        yield LocatorDef(by="css", value=".el-dialog:visible")
        yield LocatorDef(by="css", value=".el-dialog:not([style*='display: none'])")
        yield LocatorDef(by="css", value="[role='dialog']")
        return
    if name in {"弹窗关闭"}:
        yield LocatorDef(by="css", value=".el-dialog:visible .el-dialog__headerbtn")
        yield LocatorDef(by="css", value=".el-dialog .el-dialog__headerbtn")
        return
    if name in {"批量领取"}:
        yield LocatorDef(by="text", value="批量领取", exact=True)
        yield LocatorDef(by="role", value="button", name="批量领取", exact=True)
        return
    if name in {"下载中心"}:
        yield LocatorDef(by="text", value="下载中心", exact=True)
        yield LocatorDef(by="role", value="button", name="下载中心", exact=True)
        return

    for role in _ROLE_BUTTONISH:
        yield LocatorDef(by="role", value=role, name=name, exact=True)
    yield LocatorDef(by="text", value=name, exact=True)
    yield LocatorDef(by="placeholder", value=name)
    yield LocatorDef(by="label", value=name, exact=True)
    yield LocatorDef(by="testid", value=name)
    yield LocatorDef(by="xpath", value=_form_control_xpath(name))
    for role in _ROLE_BUTTONISH:
        yield LocatorDef(by="role", value=role, name=name, exact=False)


def validate_locator(page: Page, locator: LocatorDef) -> float | None:
    try:
        loc = resolve_locator(page, locator)
        count = loc.count()
    except Exception:  # noqa: BLE001
        return None
    if count < 1:
        return None
    # Prefer an enabled, visible match (skip disabled EP buttons / hidden clones).
    chosen = None
    for i in range(min(count, 8)):
        item = loc.nth(i)
        try:
            if not item.is_visible():
                continue
            try:
                if not item.is_enabled():
                    continue
            except Exception:  # noqa: BLE001
                pass
            # Reject sidebar menu labels when looking for main-content filters.
            try:
                in_aside = item.evaluate(
                    "el => !!(el.closest('aside') || el.closest('.el-menu') || el.closest('.md-sidebar'))"
                )
            except Exception:  # noqa: BLE001
                in_aside = False
            if in_aside and locator.by in {"text", "placeholder", "label"}:
                continue
            chosen = item
            break
        except Exception:  # noqa: BLE001
            continue
    if chosen is None:
        return None
    if count == 1:
        return 0.95
    return 0.8


def bind_element(
    page: Page,
    name: str,
    *,
    extra: list[LocatorDef] | None = None,
) -> tuple[LocatorDef, float] | None:
    best: tuple[LocatorDef, float] | None = None
    # LLM / extra candidates first (often more specific), then heuristics.
    ordered = list(extra or []) + list(iter_candidates(name))
    for cand in ordered:
        score = validate_locator(page, cand)
        if score is None:
            continue
        if score >= 0.9:
            return cand, score
        if best is None or score > best[1]:
            best = (cand, score)
    if best and best[1] >= _MIN_CONFIDENCE:
        return best
    return None
