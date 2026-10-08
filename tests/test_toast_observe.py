"""Phase 3 toast observe window."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.browser.session import start_playwright
from framework.paths import project_root
from framework.runner.errors import FailureCode, StepError
from framework.runner.executor import execute_case_file
from framework.schema.loader import load_case


def _run(page, name: str) -> None:
    root = project_root() / "runs" / "TOAST-001"
    execute_case_file(
        root / "yaml" / name,
        page,
        pom_dir=root / "pom",
        log_dir=root / "logs",
        req_id="TOAST-001",
    )


@pytest.fixture
def toast_page():
    playwright, browser, context, page = start_playwright()
    try:
        yield page
    finally:
        context.close()
        browser.close()
        playwright.stop()


def test_expect_success_toast(toast_page):
    _run(toast_page, "expect_success.yaml")


def test_expect_error_toast(toast_page):
    _run(toast_page, "expect_error.yaml")


def test_navigation_and_forbid_error_after_toast_gone(toast_page):
    _run(toast_page, "nav_forbid_error.yaml")


def test_forbid_error_fails_even_if_toast_disappears(toast_page):
    root = project_root() / "runs" / "TOAST-001"
    case = load_case(root / "yaml" / "expect_error.yaml")
    # Reuse the error button, but keep default forbid [error] and do not expect it.
    case.case_id = "TC_TOAST_FORBID_FAIL"
    case.steps[1].observe.toasts = []
    case.steps[1].observe.forbid_toast_levels = ["error"]
    case.steps[1].element = "跳转报错按钮"
    from framework.runner.executor import execute_case

    with pytest.raises(StepError) as caught:
        execute_case(
            case,
            toast_page,
            pom_dir=root / "pom",
            log_dir=root / "logs",
            req_id="TOAST-001",
        )
    err = caught.value
    assert err.code == FailureCode.UI_ERROR_TOAST
    toasts = (err.details or {}).get("toasts") or []
    assert any(t.get("level") == "error" and "系统异常" in (t.get("text") or "") for t in toasts)


def test_missing_expected_toast_fails(toast_page):
    root = project_root() / "runs" / "TOAST-001"
    case = load_case(root / "yaml" / "expect_success.yaml")
    case.steps[1].observe.toasts[0].contains = "并不存在的文案"
    from framework.runner.executor import execute_case

    with pytest.raises(StepError) as caught:
        execute_case(
            case,
            toast_page,
            pom_dir=root / "pom",
            log_dir=root / "logs",
            req_id="TOAST-001",
        )
    assert caught.value.code == FailureCode.ASSERT_FAIL
    assert "expected toast not seen" in caught.value.message
