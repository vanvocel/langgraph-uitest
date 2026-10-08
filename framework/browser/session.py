"""Playwright browser session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from framework.paths import load_settings
from framework.toast.listener import install_toast_bridge


def _browser_cfg() -> dict[str, Any]:
    return load_settings().get("browser") or {}


def _context_kwargs(storage_state: str | Path | None = None) -> dict[str, Any]:
    cfg = _browser_cfg()
    kwargs: dict[str, Any] = {}
    if storage_state and Path(storage_state).is_file():
        kwargs["storage_state"] = str(storage_state)
    locale = cfg.get("locale")
    if locale:
        kwargs["locale"] = locale
    headers = cfg.get("extra_http_headers")
    if headers:
        kwargs["extra_http_headers"] = dict(headers)
    return kwargs


@contextmanager
def browser_page(
    *,
    headless: bool | None = None,
    storage_state: str | Path | None = None,
) -> Iterator[Page]:
    cfg = _browser_cfg()
    if headless is None:
        headless = bool(cfg.get("headless", True))
    timeout_ms = int(cfg.get("timeout_ms", 30000))
    slow_mo = int(cfg.get("slow_mo_ms", 0))

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context: BrowserContext = browser.new_context(**_context_kwargs(storage_state))
        context.set_default_timeout(timeout_ms)
        install_toast_bridge(context)
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def start_playwright(
    storage_state: str | Path | None = None,
) -> tuple[Playwright, Browser, BrowserContext, Page]:
    """Manual lifecycle for pytest fixtures."""
    cfg = _browser_cfg()
    headless = bool(cfg.get("headless", True))
    timeout_ms = int(cfg.get("timeout_ms", 30000))
    slow_mo = int(cfg.get("slow_mo_ms", 0))

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
    context = browser.new_context(**_context_kwargs(storage_state))
    context.set_default_timeout(timeout_ms)
    install_toast_bridge(context)
    page = context.new_page()
    return p, browser, context, page
