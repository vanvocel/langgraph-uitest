"""Phase 1/2: execute YAML cases under runs/<req>/ via tool runner."""

from __future__ import annotations

from pathlib import Path

import allure
import pytest

from framework.bootstrap.login import storage_state_for
from framework.browser.session import start_playwright
from framework.paths import init_requirement, load_settings, req_dir
from framework.runner.executor import execute_case_file
from framework.schema.loader import list_case_files, load_case


def _case_files(req: str) -> list[Path]:
    init_requirement(req)
    return list_case_files(req_dir(req) / "yaml")


def _peek_account_ref(cases: list[Path]) -> str | None:
    for path in cases:
        case = load_case(path)
        for pre in case.preconditions:
            if pre.auth == "logged_in":
                if pre.account_ref:
                    return pre.account_ref
                cfg = (load_settings().get("bootstrap") or {}).get("login") or {}
                return cfg.get("default_account_ref") or "default_tester"
    return None


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "yaml_case_path" not in metafunc.fixturenames:
        return
    req = metafunc.config.getoption("--req")
    if not req:
        metafunc.parametrize("yaml_case_path", [None], ids=["no-req"])
        return
    files = _case_files(req)
    if not files:
        metafunc.parametrize("yaml_case_path", [None], ids=["no-yaml"])
        return
    metafunc.parametrize("yaml_case_path", files, ids=[p.stem for p in files])


@pytest.fixture(scope="module")
def req_runtime(req_id: str | None):
    if not req_id:
        yield None
        return
    cases = _case_files(req_id)
    account_ref = _peek_account_ref(cases)
    state = storage_state_for(account_ref) if account_ref else None
    playwright, browser, context, page = start_playwright(storage_state=state)
    try:
        yield {
            "page": page,
            "pom_dir": req_dir(req_id) / "pom",
            "log_dir": req_dir(req_id) / "logs",
        }
    finally:
        context.close()
        browser.close()
        playwright.stop()


@pytest.mark.req
def test_yaml_case(req_id: str | None, yaml_case_path: Path | None, req_runtime):
    if not req_id:
        pytest.skip("pass --req <id> to run requirement YAML cases")
    if yaml_case_path is None:
        pytest.fail(f"no YAML cases under runs/{req_id}/yaml")

    allure.dynamic.epic(req_id)
    allure.dynamic.feature(yaml_case_path.stem)
    execute_case_file(
        yaml_case_path,
        req_runtime["page"],
        pom_dir=req_runtime["pom_dir"],
        log_dir=req_runtime["log_dir"],
        req_id=req_id,
    )
