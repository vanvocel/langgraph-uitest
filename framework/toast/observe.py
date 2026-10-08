"""Observation window: toast expect/forbid judged together with navigation."""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Page

from framework.runner.errors import FailureCode, StepError
from framework.schema.case import ActionName, ObserveSpec, ToastExpect, UiCase
from framework.toast.listener import arm_toast_listener, load_toast_rules, toasts_since

_SIDE_EFFECTS = {
    ActionName.click,
    ActionName.click_if_visible,
    ActionName.fill,
    ActionName.select,
    ActionName.multi_select,
    ActionName.clear_select,
    ActionName.hover,
}

# open / click_if_visible 常带出页面接口的「请求失败」等背景 toast，不阻断后续步骤。
# 若某步需要盯 toast，在该步骤自己写 observe。
_NAV_ONLY = {ActionName.open, ActionName.click_if_visible}


def merge_observe(case: UiCase, step_observe: ObserveSpec | None, action: ActionName) -> ObserveSpec | None:
    """Merge framework default, case defaults, and step observe.

    Side-effect actions get default forbid [error] unless explicitly overridden.
    Pure asserts are not watched unless the step itself sets observe.
    ``open`` does not inherit case/framework toast forbid (incidental page-load toasts).
    """
    rules = load_toast_rules()
    case_obs = None
    if case.defaults and case.defaults.on_action:
        case_obs = case.defaults.on_action.observe

    if action in _NAV_ONLY and step_observe is None:
        return None

    side = action in _SIDE_EFFECTS
    if step_observe is None and not side:
        return None

    data: dict[str, Any] = {
        "window_ms": int(rules.get("default_window_ms", 3000)),
        "toasts": [],
        "forbid_toast_levels": list(rules.get("default_forbid_levels") or ["error"]),
        "navigation": None,
    }
    if not side:
        data["forbid_toast_levels"] = []

    sources = (step_observe,) if action in _NAV_ONLY else (case_obs, step_observe)
    for obs in sources:
        if obs is None:
            continue
        dumped = obs.model_dump(exclude_unset=True)
        if "window_ms" in dumped:
            data["window_ms"] = dumped["window_ms"]
        if "forbid_toast_levels" in dumped:
            data["forbid_toast_levels"] = dumped["forbid_toast_levels"]
        if "navigation" in dumped and dumped["navigation"] is not None:
            data["navigation"] = dumped["navigation"]
        if dumped.get("toasts"):
            data["toasts"] = dumped["toasts"]

    return ObserveSpec.model_validate(data)


def _matches(rule: ToastExpect, toast: dict[str, Any], *, field: str) -> bool:
    level = getattr(rule, field)
    if level is None or toast.get("level") != level:
        return False
    if rule.contains and rule.contains not in (toast.get("text") or ""):
        return False
    return True


def _expected(observe: ObserveSpec, toast: dict[str, Any]) -> bool:
    return any(_matches(rule, toast, field="expect") for rule in observe.toasts)


def _forbidden(observe: ObserveSpec, toast: dict[str, Any]) -> bool:
    if _expected(observe, toast):
        return False
    levels = observe.forbid_toast_levels or []
    if toast.get("level") in levels:
        return True
    return any(_matches(rule, toast, field="forbid") for rule in observe.toasts)


def _missing_expects(observe: ObserveSpec, toasts: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for rule in observe.toasts:
        if not rule.expect:
            continue
        if not any(_matches(rule, t, field="expect") for t in toasts):
            text = rule.contains or "*"
            missing.append(f"{rule.expect}:{text}")
    return missing


def _nav_ok(page: Page, observe: ObserveSpec, ctx: Any) -> bool:
    nav = observe.navigation
    if nav is None:
        return True
    url = page.url or ""
    if nav.expect_url and url.rstrip("/") != nav.expect_url.rstrip("/"):
        return False
    if nav.expect_url_contains and nav.expect_url_contains not in url:
        return False
    if nav.expect_element:
        if ctx is None:
            return False
        try:
            loc = ctx.get_locator(nav.expect_element)
            if not loc.first.is_visible():
                return False
        except Exception:
            return False
    return True


def judge_observe(
    page: Page,
    observe: ObserveSpec,
    cursor: int,
    ctx: Any = None,
) -> list[dict[str, Any]]:
    """Poll toasts + navigation until satisfied or window ends.

    Listener must already be armed (cursor) before the action.
    """
    rules = load_toast_rules()
    settle_s = int(rules.get("settle_ms", 800)) / 1000
    window_s = max(observe.window_ms, 0) / 1000
    has_expect = any(rule.expect for rule in observe.toasts)
    # Forbid-only still waits at least settle_ms so a late error toast is caught.
    if not has_expect and observe.navigation is None:
        window_s = max(window_s, settle_s)
    started = time.monotonic()
    deadline = started + window_s

    latest: list[dict[str, Any]] = []
    while True:
        latest = toasts_since(page, cursor)
        for toast in latest:
            if _forbidden(observe, toast):
                raise StepError(
                    FailureCode.UI_ERROR_TOAST,
                    f"forbidden toast: [{toast.get('level')}] {toast.get('text')}",
                    expected="no " + ",".join(observe.forbid_toast_levels or []),
                    actual=str(toast.get("text")),
                    details={"toasts": latest},
                )
        missing = _missing_expects(observe, latest)
        nav_ok = _nav_ok(page, observe, ctx)
        elapsed = time.monotonic() - started
        if not missing and nav_ok and elapsed >= settle_s:
            return latest
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(100)

    latest = toasts_since(page, cursor)
    for toast in latest:
        if _forbidden(observe, toast):
            raise StepError(
                FailureCode.UI_ERROR_TOAST,
                f"forbidden toast: [{toast.get('level')}] {toast.get('text')}",
                actual=str(toast.get("text")),
                details={"toasts": latest},
            )
    missing = _missing_expects(observe, latest)
    if missing:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "expected toast not seen: " + ", ".join(missing),
            expected=", ".join(missing),
            actual=str(latest),
            details={"toasts": latest},
        )
    if not _nav_ok(page, observe, ctx):
        nav = observe.navigation
        expected = ""
        if nav:
            expected = nav.expect_url or nav.expect_url_contains or nav.expect_element or ""
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"navigation not reached: {expected}",
            expected=expected,
            actual=page.url,
            details={"toasts": latest},
        )
    return latest


def begin_observe(page: Page, observe: ObserveSpec | None) -> int | None:
    if observe is None:
        return None
    return arm_toast_listener(page)
