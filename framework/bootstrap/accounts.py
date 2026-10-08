"""Load account configs and resolve credentials from env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from framework.paths import project_root
from framework.runner.errors import FailureCode, StepError


class OrgSelectConfig(BaseModel):
    mode: Literal["none", "fixed", "auto"] = "auto"
    value: str | None = None
    wait_ms: int = 5000


class AccountConfig(BaseModel):
    description: str | None = None
    username_env: str
    password_env: str
    org_select: OrgSelectConfig = Field(default_factory=OrgSelectConfig)


class ResolvedAccount(BaseModel):
    account_ref: str
    username: str
    password: str
    org_select: OrgSelectConfig


def load_accounts_file() -> dict[str, Any]:
    path = project_root() / "config" / "accounts.yaml"
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("accounts") or {}


def resolve_account(account_ref: str) -> ResolvedAccount:
    accounts = load_accounts_file()
    if account_ref not in accounts:
        raise StepError(
            FailureCode.ENV_ERROR,
            f"unknown account_ref: {account_ref!r}",
        )
    cfg = AccountConfig.model_validate(accounts[account_ref])
    username = os.getenv(cfg.username_env, "").strip()
    password = os.getenv(cfg.password_env, "").strip()
    if not username or not password:
        raise StepError(
            FailureCode.ENV_ERROR,
            f"missing credentials for {account_ref}: "
            f"set {cfg.username_env} / {cfg.password_env} in .env",
        )
    if cfg.org_select.mode in {"fixed", "auto"} and not cfg.org_select.value:
        raise StepError(
            FailureCode.ENV_ERROR,
            f"account {account_ref} org_select.mode={cfg.org_select.mode} needs value",
        )
    return ResolvedAccount(
        account_ref=account_ref,
        username=username,
        password=password,
        org_select=cfg.org_select,
    )


def auth_state_path(account_ref: str) -> Path:
    from framework.paths import load_settings

    settings = load_settings()
    auth_root = project_root() / (settings.get("paths") or {}).get("auth_root", ".auth")
    auth_root.mkdir(parents=True, exist_ok=True)
    safe = account_ref.replace("/", "_").replace("\\", "_")
    return auth_root / f"{safe}.json"
