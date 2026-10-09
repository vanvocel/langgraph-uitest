"""Reveal page states by following safe navigation steps from YAML cases."""

from __future__ import annotations

from playwright.sync_api import Page

from framework.agents.discover.candidates import bind_element
from framework.pom.loader import resolve_locator
from framework.schema.case import ActionName, Step, UiCase

# Only these actions are used to reach a state for binding (no fill/assert).
_REVEAL_ACTIONS = {
    ActionName.open,
    ActionName.click,
    ActionName.click_if_visible,
    ActionName.wait_visible,
}

# Never auto-click these during reveal (destructive / commit).
_BLOCKED_CLICK_NAMES = {
    "确认",
    "确认添加",
    "已知风险仍保存",
    "删除",
    "移除",
}

# Include this click, then stop — opens a useful state for binding.
_STOP_AFTER_CLICK = {
    "添加渠道",  # channel picker dialog
    "保存",  # may open layer-diff / validation dialog
}


def extract_reveal_steps(case: UiCase) -> list[Step]:
    """Take leading navigation steps until first non-reveal / blocked / stop-after."""
    out: list[Step] = []
    for step in case.steps:
        if step.action not in _REVEAL_ACTIONS:
            break
        if step.action in {ActionName.click, ActionName.click_if_visible}:
            name = (step.element or "").strip()
            if name in _BLOCKED_CLICK_NAMES:
                break
            out.append(step)
            if name in _STOP_AFTER_CLICK:
                break
            continue
        out.append(step)
    return out


def _click_by_name(page: Page, name: str, *, optional: bool) -> bool:
    want = "".join((name or "").split())

    def _pick_and_click(locator) -> bool:
        for i in range(min(locator.count(), 8)):
            item = locator.nth(i)
            try:
                if not item.is_visible() or not item.is_enabled():
                    continue
                text = "".join((item.inner_text() or "").split())
                aria = "".join((item.get_attribute("aria-label") or "").split())
                if want and text and text != want and want in text:
                    continue
                if want and aria and aria != want and want in aria:
                    continue
                item.click(timeout=4000)
                page.wait_for_timeout(500)
                return True
            except Exception:  # noqa: BLE001
                continue
        return False

    hit = bind_element(page, name)
    if hit is not None:
        try:
            if _pick_and_click(resolve_locator(page, hit[0])):
                return True
        except Exception:  # noqa: BLE001
            pass
    try:
        tab = page.get_by_role("tab", name=name, exact=True)
        if tab.count() and _pick_and_click(tab):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        btn = page.get_by_role("button", name=name, exact=True)
        if btn.count() and _pick_and_click(btn):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False if optional else False


def apply_reveal_steps(
    page: Page,
    steps: list[Step],
    *,
    fixture_dir=None,
    base_url: str | None = None,
) -> list[str]:
    """Execute reveal steps on the live page. Returns log of applied actions."""
    from framework.tools.actions import ToolContext, tool_open

    applied: list[str] = []
    ctx = ToolContext(page, elements={}, base_url=base_url, fixture_dir=fixture_dir)
    for step in steps:
        if step.action == ActionName.open:
            tool_open(ctx, step)
            page.wait_for_timeout(600)
            applied.append(f"open:{step.url or step.value}")
            continue
        name = (step.element or "").strip()
        if not name:
            continue
        if step.action == ActionName.wait_visible:
            hit = bind_element(page, name)
            if hit:
                try:
                    resolve_locator(page, hit[0]).first.wait_for(state="visible", timeout=5000)
                    applied.append(f"wait:{name}")
                except Exception:  # noqa: BLE001
                    applied.append(f"wait_skip:{name}")
            else:
                # Semantic waits (弹窗名) — wait for any visible dialog briefly.
                if name in {"渠道选择器", "层差校验弹窗", "层差不通过提示", "二次确认", "弹窗"}:
                    try:
                        page.locator(".el-dialog:visible, [role='dialog']").first.wait_for(
                            state="visible", timeout=4000
                        )
                        applied.append(f"wait_dialog:{name}")
                    except Exception:  # noqa: BLE001
                        applied.append(f"wait_skip:{name}")
                else:
                    applied.append(f"wait_skip:{name}")
            continue
        optional = step.action == ActionName.click_if_visible
        ok = _click_by_name(page, name, optional=optional)
        applied.append(f"{'click_ok' if ok else 'click_fail'}:{name}")
        if ok and name in {"清洗评分规则", "人工待清洗", "修改", "添加渠道", "保存"}:
            try:
                page.evaluate("() => window.scrollTo(0, Math.min(600, document.body.scrollHeight/3))")
            except Exception:  # noqa: BLE001
                pass
            if name in {"添加渠道", "保存"}:
                page.wait_for_timeout(600)
    return applied


def dismiss_overlays(page: Page) -> list[str]:
    """Best-effort close dialogs so the next reveal path starts clean."""
    log: list[str] = []
    for _ in range(2):
        try:
            cancel = page.get_by_role("button", name="取消", exact=True)
            for i in range(min(cancel.count(), 4)):
                item = cancel.nth(i)
                if item.is_visible() and item.is_enabled():
                    item.click(timeout=2000)
                    page.wait_for_timeout(300)
                    log.append("click:取消")
                    break
        except Exception:  # noqa: BLE001
            pass
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
            log.append("escape")
        except Exception:  # noqa: BLE001
            pass
        try:
            dlg = page.locator(".el-dialog:visible")
            if dlg.count() < 1:
                break
        except Exception:  # noqa: BLE001
            break
    return log


def _path_rank(steps: list[Step]) -> int:
    names = [(s.element or "") for s in steps]
    if "添加渠道" in names:
        return 2
    if "保存" in names:
        return 3
    if "修改" in names:
        return 1
    return 0


def unique_reveal_paths(cases: list[UiCase]) -> list[tuple[str, list[Step]]]:
    """Deduplicate reveal paths; edit → channel dialog → save dialog."""
    seen: set[str] = set()
    paths: list[tuple[str, list[Step]]] = []
    ordered = sorted(cases, key=lambda c: (_path_rank(extract_reveal_steps(c)), c.case_id))
    for case in ordered:
        steps = extract_reveal_steps(case)
        if not steps:
            continue
        key = "|".join(
            f"{s.action.value}:{s.element or s.url or s.value or ''}" for s in steps
        )
        if key in seen:
            continue
        seen.add(key)
        paths.append((case.case_id, steps))
    return paths
