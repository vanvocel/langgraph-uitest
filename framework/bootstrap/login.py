"""Generic login bootstrap with optional organization selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import allure
import yaml
from playwright.sync_api import Page

from framework.bootstrap.accounts import ResolvedAccount, auth_state_path, resolve_account
from framework.paths import load_settings, project_root
from framework.pom.loader import LocatorDef, resolve_locator
from framework.runner.errors import FailureCode, StepError


def _login_settings() -> dict[str, Any]:
    settings = load_settings()
    return (settings.get("bootstrap") or {}).get("login") or {}


def _load_login_pom() -> dict[str, LocatorDef]:
    path = project_root() / "framework" / "bootstrap" / "login_pom.yaml"
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    elements = raw.get("elements") or {}
    return {name: LocatorDef.model_validate(defn) for name, defn in elements.items()}


def _loc(page: Page, elements: dict[str, LocatorDef], name: str):
    if name not in elements:
        raise StepError(FailureCode.BIND_ERROR, f"login POM missing element: {name}")
    return resolve_locator(page, elements[name]).first


def _already_logged_in(page: Page, success_contains: str) -> bool:
    url = page.url or ""
    if success_contains and success_contains in url:
        return True
    return False


def _select_org_if_needed(page: Page, elements: dict[str, LocatorDef], account: ResolvedAccount) -> str:
    """Apply org_select strategy. Returns action taken for logging."""
    mode = account.org_select.mode
    if mode == "none":
        return "org_skipped_mode_none"

    wait_ms = account.org_select.wait_ms
    value = account.org_select.value
    org = _loc(page, elements, "组织下拉")
    appeared = False
    try:
        org.wait_for(state="visible", timeout=wait_ms)
        appeared = True
    except Exception:
        appeared = False

    if not appeared:
        if mode == "fixed":
            raise StepError(
                FailureCode.ENV_ERROR,
                f"org_select.mode=fixed but organization dropdown did not appear "
                f"within {wait_ms}ms",
            )
        return "org_skipped_not_visible"

    assert value is not None
    try:
        org.click(timeout=wait_ms)
        page.get_by_role("option", name=value).first.click(timeout=wait_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"failed to select organization {value!r}: {exc}",
            element="组织下拉",
        ) from exc
    return f"org_selected:{value}"


def perform_ui_login(page: Page, account: ResolvedAccount, *, login_cfg: dict[str, Any] | None = None) -> None:
    cfg = login_cfg or _login_settings()
    login_url = cfg.get("login_url") or "https://login.z-niu.com/"
    success_contains = cfg.get("success_url_contains") or "main.z-niu.com"
    elements = _load_login_pom()

    with allure.step(f"bootstrap login (account={account.account_ref})"):
        page.goto(login_url, wait_until="domcontentloaded")
        _loc(page, elements, "用户名输入框").fill(account.username)
        org_result = _select_org_if_needed(page, elements, account)
        allure.attach(org_result, name="org_select", attachment_type=allure.attachment_type.TEXT)
        _loc(page, elements, "密码输入框").fill(account.password)
        _loc(page, elements, "登录按钮").click()
        try:
            import re

            pattern = re.compile(".*" + re.escape(success_contains) + ".*")
            page.wait_for_url(pattern, timeout=20000)
        except Exception as exc:  # noqa: BLE001
            raise StepError(
                FailureCode.ENV_ERROR,
                f"login did not reach url containing {success_contains!r}; "
                f"current={page.url!r}: {exc}",
            ) from exc

        state_path = auth_state_path(account.account_ref)
        page.context.storage_state(path=str(state_path))
        allure.attach(
            str(state_path),
            name="storage_state_saved",
            attachment_type=allure.attachment_type.TEXT,
        )


def ensure_logged_in(
    page: Page,
    *,
    account_ref: str | None = None,
    reuse_storage_state: bool | None = None,
    force_ui_login: bool | None = None,
) -> ResolvedAccount:
    """Ensure page session is authenticated for account_ref."""
    cfg = _login_settings()
    if not cfg.get("enabled", True):
        raise StepError(FailureCode.ENV_ERROR, "bootstrap.login.enabled is false")

    ref = account_ref or cfg.get("default_account_ref") or "default_tester"
    account = resolve_account(ref)
    success_contains = cfg.get("success_url_contains") or "main.z-niu.com"
    land_url = cfg.get("land_url") or f"https://{success_contains}/"
    reuse = cfg.get("reuse_storage_state", True) if reuse_storage_state is None else reuse_storage_state
    force = cfg.get("force_ui_login", False) if force_ui_login is None else force_ui_login

    state_path = auth_state_path(ref)
    if force:
        perform_ui_login(page, account, login_cfg=cfg)
        return account

    # If current page already looks logged in, keep it.
    if _already_logged_in(page, success_contains):
        return account

    # Try storage_state by navigating to land_url; if bounced to login, re-login.
    if reuse and state_path.is_file():
        # Cookies already in context only if context was created with storage_state.
        # Still try land_url; if session cookies present they work.
        try:
            page.goto(land_url, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            if _already_logged_in(page, success_contains) and "login." not in page.url:
                return account
        except Exception:
            pass

    perform_ui_login(page, account, login_cfg=cfg)
    if land_url:
        page.goto(land_url, wait_until="domcontentloaded")
    return account


def storage_state_for(account_ref: str | None = None) -> Path | None:
    """Return existing storage_state path for account, or None."""
    cfg = _login_settings()
    ref = account_ref or cfg.get("default_account_ref") or "default_tester"
    path = auth_state_path(ref)
    return path if path.is_file() else None
