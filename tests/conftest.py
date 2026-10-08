"""Shared fixtures for Phase 0+."""

from __future__ import annotations

import os
from pathlib import Path

import allure
import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--req",
        action="store",
        default=None,
        help="Requirement id under runs/<req>/",
    )


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def req_id(pytestconfig: pytest.Config) -> str | None:
    return pytestconfig.getoption("--req")


@pytest.fixture
def allure_env():
    """Attach basic environment info into Allure."""
    allure.dynamic.parameter("BASE_URL", os.getenv("BASE_URL", ""))
    yield


@pytest.fixture(scope="session")
def browser_type_launch_args():
    from framework.paths import load_settings

    cfg = load_settings().get("browser") or {}
    return {
        "headless": bool(cfg.get("headless", True)),
        "slow_mo": int(cfg.get("slow_mo_ms", 0)),
    }


@pytest.fixture
def page():
    """Sync Playwright page (function-scoped)."""
    from framework.browser.session import start_playwright

    playwright, browser, context, page = start_playwright()
    try:
        yield page
    finally:
        context.close()
        browser.close()
        playwright.stop()
