"""YAML case executor: step → tool, with Allure + structured logs."""

from __future__ import annotations

import json
from pathlib import Path

import allure
from playwright.sync_api import Page

from framework.bootstrap.login import ensure_logged_in
from framework.pom.loader import load_pom
from framework.runner.errors import FailureCode, StepError
from framework.runner.logging import RunLogger
from framework.runner.screenshot import take_png
from framework.schema.case import ActionName, ObserveSpec, UiCase
from framework.schema.loader import load_case
from framework.toast.observe import begin_observe, judge_observe, merge_observe
from framework.tools.actions import ToolContext, run_action


def _merge_observe(case: UiCase, step) -> ObserveSpec | None:
    return merge_observe(case, step.observe, step.action)


def _apply_preconditions(case: UiCase, page: Page, logger: RunLogger) -> None:
    for pre in case.preconditions:
        if pre.auth == "logged_in":
            with allure.step(f"precondition: auth=logged_in ({pre.account_ref or 'default'})"):
                account = ensure_logged_in(page, account_ref=pre.account_ref)
                logger.write(
                    "precondition_login",
                    account_ref=account.account_ref,
                    org_mode=account.org_select.mode,
                    url=page.url,
                )
                allure.dynamic.parameter("account_ref", account.account_ref)


def _is_assert(action: ActionName) -> bool:
    return action.value.startswith("assert_")


def _attach_screenshot(page: Page, name: str, *, dest: Path | None = None) -> bytes | None:
    png = take_png(page)
    if not png:
        return None
    allure.attach(png, name=name, attachment_type=allure.attachment_type.PNG)
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png)
    return png


def execute_case(
    case: UiCase,
    page: Page,
    *,
    pom_dir: Path,
    log_dir: Path,
    req_id: str,
    live_bind: bool = True,
) -> None:
    pom = load_pom(pom_dir)
    fixture_dir = pom_dir.parent / "fixtures"
    shot_dir = log_dir / "screenshots"
    pom_path = pom_dir / "elements.yaml"
    logger = RunLogger(log_dir / f"{case.case_id}.jsonl", case_id=case.case_id, req_id=req_id)

    def _on_live_bind(name: str, loc, score: float) -> None:
        logger.write(
            "live_bind",
            element=name,
            by=loc.by,
            value=loc.value,
            name_attr=loc.name,
            confidence=score,
        )

    ctx = ToolContext(
        page,
        elements=dict(pom.elements),
        base_url=case.base_url or pom.url,
        fixture_dir=fixture_dir if fixture_dir.is_dir() else None,
        live_bind=live_bind,
        # JIT uses heuristics only; LLM discover owns POM writes.
        live_bind_llm=False,
        # Do not overwrite discover POM from flaky runtime binds.
        pom_path=None,
        on_live_bind=_on_live_bind,
    )
    logger.write("case_start", title=case.title, steps=len(case.steps), live_bind=live_bind)

    allure.dynamic.epic(case.requirement_id or req_id)
    allure.dynamic.feature(case.case_id)
    allure.dynamic.title(case.title)
    allure.dynamic.parameter("case_id", case.case_id)
    allure.dynamic.parameter("req_id", req_id)

    try:
        _apply_preconditions(case, page, logger)

        for index, step in enumerate(case.steps, start=1):
            label = step.description or f"{step.action.value}" + (
                f" · {step.element}" if step.element else ""
            )
            case_png: bytes | None = None
            case_png_name = ""
            step_error: StepError | None = None
            with allure.step(f"[{index}] {label}"):
                logger.write(
                    "step_start",
                    step_index=index,
                    action=step.action.value,
                    element=step.element,
                    value=step.value,
                    url=step.url,
                    expect=step.expect,
                )
                try:
                    observe = _merge_observe(case, step)
                    cursor = begin_observe(page, observe)
                    run_action(ctx, step)
                    toasts: list = []
                    if observe is not None and cursor is not None:
                        toasts = judge_observe(page, observe, cursor, ctx)
                except StepError as err:
                    # One JIT rebind + retry when locator miss / wait fails.
                    retried = False
                    if (
                        live_bind
                        and err.code in {FailureCode.BIND_ERROR, FailureCode.ASSERT_FAIL}
                        and step.element
                        and step.action
                        in {
                            ActionName.wait_visible,
                            ActionName.click,
                            ActionName.click_if_visible,
                            ActionName.fill,
                            ActionName.assert_visible,
                        }
                    ):
                        rebound = ctx._try_live_bind(
                            step.element,
                            exclude_current=step.element in ctx.elements,
                        )
                        if rebound is not None:
                            try:
                                run_action(ctx, step)
                                toasts = []
                                if observe is not None and cursor is not None:
                                    toasts = judge_observe(page, observe, cursor, ctx)
                                retried = True
                                logger.write(
                                    "step_retry_ok",
                                    step_index=index,
                                    element=step.element,
                                    via="live_bind",
                                )
                            except StepError as err2:
                                err = err2
                            except Exception as exc:  # noqa: BLE001
                                err = StepError(
                                    FailureCode.UNKNOWN,
                                    str(exc),
                                    step_index=index,
                                    action=step.action.value,
                                    element=step.element,
                                )
                    if retried:
                        if _is_assert(step.action):
                            png_name = f"断言通过 [{index}] {step.action.value}"
                            case_png = _attach_screenshot(
                                page,
                                png_name,
                                dest=shot_dir / f"{case.case_id}_{index:02d}_{step.action.value}.png",
                            )
                            case_png_name = png_name
                        logger.write(
                            "step_ok",
                            step_index=index,
                            action=step.action.value,
                            url=page.url,
                            toasts=toasts,
                            live_bind_retry=True,
                        )
                    else:
                        err.step_index = index
                        err.action = err.action or step.action.value
                        err.element = err.element or step.element
                        fail_name = f"断言失败 [{index}] {step.action.value}"
                        case_png = _attach_failure(
                            page, logger, err, shot_dir / f"{case.case_id}_{index:02d}_fail.png", shot_name=fail_name
                        )
                        case_png_name = fail_name
                        step_error = err
                except Exception as exc:  # noqa: BLE001
                    err = StepError(
                        FailureCode.UNKNOWN,
                        str(exc),
                        step_index=index,
                        action=step.action.value,
                        element=step.element,
                    )
                    fail_name = f"步骤失败 [{index}] {step.action.value}"
                    case_png = _attach_failure(
                        page, logger, err, shot_dir / f"{case.case_id}_{index:02d}_fail.png", shot_name=fail_name
                    )
                    case_png_name = fail_name
                    step_error = err
                else:
                    if _is_assert(step.action):
                        png_name = f"断言通过 [{index}] {step.action.value}"
                        case_png = _attach_screenshot(
                            page,
                            png_name,
                            dest=shot_dir / f"{case.case_id}_{index:02d}_{step.action.value}.png",
                        )
                        case_png_name = png_name
                        if step.expect is not None:
                            allure.attach(
                                step.expect,
                                name="expect",
                                attachment_type=allure.attachment_type.TEXT,
                            )
                    logger.write(
                        "step_ok",
                        step_index=index,
                        action=step.action.value,
                        url=page.url,
                        toasts=toasts,
                    )
            if case_png:
                allure.attach(
                    case_png,
                    name=case_png_name,
                    attachment_type=allure.attachment_type.PNG,
                )
            if step_error is not None:
                raise step_error
        logger.write("case_pass", url=page.url)
    except StepError as err:
        logger.write("case_fail", **err.to_dict())
        raise


def execute_case_file(
    case_path: Path,
    page: Page,
    *,
    pom_dir: Path,
    log_dir: Path,
    req_id: str,
) -> UiCase:
    case = load_case(case_path)
    if case.requirement_id is None:
        case.requirement_id = req_id
    execute_case(case, page, pom_dir=pom_dir, log_dir=log_dir, req_id=req_id)
    return case


def _attach_failure(
    page: Page,
    logger: RunLogger,
    err: StepError,
    shot_path: Path,
    *,
    shot_name: str = "断言失败/步骤失败",
) -> bytes | None:
    logger.write("step_fail", **err.to_dict())
    allure.attach(
        json.dumps(err.to_dict(), ensure_ascii=False, indent=2),
        name="failure",
        attachment_type=allure.attachment_type.JSON,
    )
    png = _attach_screenshot(page, shot_name, dest=shot_path)
    try:
        allure.attach(page.url, name="url", attachment_type=allure.attachment_type.TEXT)
    except Exception:  # noqa: BLE001
        pass
    return png
