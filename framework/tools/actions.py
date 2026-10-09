"""Basic UI action and assertion tools (no LLM)."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from framework.pom.loader import LocatorDef, resolve_locator
from framework.runner.errors import FailureCode, StepError
from framework.schema.case import ActionName, NavigationObserve, ObserveSpec, Step

if TYPE_CHECKING:
    from playwright.sync_api import Page


class ToolContext:
    def __init__(
        self,
        page: Page,
        *,
        elements: dict[str, LocatorDef],
        base_url: str | None = None,
        fixture_dir: Path | None = None,
        live_bind: bool = False,
        live_bind_llm: bool = True,
        pom_path: Path | None = None,
        on_live_bind: Callable[[str, LocatorDef, float], None] | None = None,
    ) -> None:
        self.page = page
        self.elements = elements
        self.base_url = (base_url or "").rstrip("/")
        self.fixture_dir = fixture_dir
        self.vars: dict[str, list[str] | str] = {}
        self.live_bind = live_bind
        self.live_bind_llm = live_bind_llm
        self.pom_path = pom_path
        self.on_live_bind = on_live_bind
        self.live_bound: dict[str, LocatorDef] = {}

    def _try_live_bind(
        self,
        element_name: str,
        *,
        exclude_current: bool = False,
    ) -> LocatorDef | None:
        if not self.live_bind:
            return None
        from framework.agents.discover.live_bind import live_bind_element, persist_binding

        exclude = self.elements.get(element_name) if exclude_current else None
        hit = live_bind_element(
            self.page,
            element_name,
            use_llm=self.live_bind_llm,
            exclude=exclude,
        )
        if hit is None:
            return None
        loc, score = hit
        self.elements[element_name] = loc
        self.live_bound[element_name] = loc
        if self.pom_path is not None:
            try:
                persist_binding(self.pom_path, element_name, loc)
            except Exception:  # noqa: BLE001
                pass
        if self.on_live_bind is not None:
            try:
                self.on_live_bind(element_name, loc, score)
            except Exception:  # noqa: BLE001
                pass
        return loc

    def get_locator(self, element_name: str):
        loc_def = self.elements.get(element_name)
        if loc_def is None:
            # Missing from POM → JIT bind on current page state only.
            loc_def = self._try_live_bind(element_name)
            if loc_def is None:
                raise StepError(
                    FailureCode.BIND_ERROR,
                    f"element not in POM: {element_name!r}",
                    element=element_name,
                )
        try:
            return resolve_locator(self.page, loc_def)
        except StepError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StepError(
                FailureCode.BIND_ERROR,
                f"failed to resolve locator for {element_name!r}: {exc}",
                element=element_name,
            ) from exc

    def abs_url(self, url: str) -> str:
        if re.match(r"^https?://", url, re.I) or url.startswith("file:"):
            return url
        # fixture://login.html or base_url=fixture:// + url=login.html
        if url.startswith("fixture://"):
            return self._fixture_url(url[len("fixture://") :])
        if self.base_url.startswith("fixture:"):
            rel = url.lstrip("/")
            return self._fixture_url(rel)
        if not self.base_url:
            raise StepError(
                FailureCode.ENV_ERROR,
                f"relative url {url!r} but base_url is empty",
            )
        return urljoin(self.base_url + "/", url.lstrip("/"))

    def _fixture_url(self, relative: str) -> str:
        if self.fixture_dir is None:
            raise StepError(
                FailureCode.ENV_ERROR,
                "fixture:// used but fixture_dir is not set",
            )
        path = (self.fixture_dir / relative.lstrip("/")).resolve()
        if not path.is_file():
            raise StepError(
                FailureCode.ENV_ERROR,
                f"fixture file not found: {path}",
            )
        return path.as_uri()


def tool_open(ctx: ToolContext, step: Step) -> None:
    url = step.url or step.value
    assert url is not None
    target = ctx.abs_url(url)
    try:
        ctx.page.goto(target, wait_until="domcontentloaded")
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.ENV_ERROR,
            f"open failed: {target}: {exc}",
            action=step.action.value,
        ) from exc


def tool_click(ctx: ToolContext, step: Step) -> None:
    assert step.element
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms or 5000
    # Prefer a visible+enabled match whose text equals the element name when possible
    # (avoids clicking 修改日志 when POM says 修改 with exact=false).
    target = loc.first
    try:
        want = "".join((step.element or "").split())
        n = min(loc.count(), 8)
        for i in range(n):
            item = loc.nth(i)
            try:
                if not item.is_visible() or not item.is_enabled():
                    continue
            except Exception:  # noqa: BLE001
                continue
            if want:
                try:
                    text = "".join((item.inner_text() or "").split())
                    aria = "".join((item.get_attribute("aria-label") or "").split())
                except Exception:  # noqa: BLE001
                    text = aria = ""
                if text and text != want and want in text:
                    continue
                if aria and aria != want and want in aria:
                    continue
            target = item
            break
    except Exception:  # noqa: BLE001
        target = loc.first
    try:
        target.click(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        try:
            target.click(timeout=timeout, force=True)
            return
        except Exception:
            pass
        raise StepError(
            FailureCode.BIND_ERROR,
            f"click failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def _is_fillable_node(item) -> bool:
    try:
        return bool(
            item.evaluate(
                """el => {
                  if (!el) return false;
                  const tag = (el.tagName || '').toLowerCase();
                  if (tag === 'input' || tag === 'textarea') return true;
                  if (el.isContentEditable) return true;
                  return false;
                }"""
            )
        )
    except Exception:  # noqa: BLE001
        return False


def _fillable(ctx: ToolContext, loc, timeout: int):
    """Prefer a real input under the locator (avoid filling th/td/labels)."""
    inner = loc.locator("input, textarea, [contenteditable='true']")
    try:
        if inner.count() >= 1:
            for i in range(min(inner.count(), 8)):
                item = inner.nth(i)
                try:
                    if item.is_visible():
                        return item
                except Exception:  # noqa: BLE001
                    continue
            return inner.first
    except Exception:  # noqa: BLE001
        pass
    first = loc.first
    if _is_fillable_node(first):
        return first
    return None


def tool_fill(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.value is not None
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms or 5000
    target = _fillable(ctx, loc, timeout)
    if target is None:
        raise StepError(
            FailureCode.BIND_ERROR,
            f"fill refused on {step.element!r}: locator is not an input/textarea",
            action=step.action.value,
            element=step.element,
        )
    try:
        target.fill(step.value, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"fill failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_select(ctx: ToolContext, step: Step) -> None:
    """Native <select> first; custom dropdowns (Element Plus etc.) click option by text."""
    assert step.element and step.value is not None
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms
    try:
        loc.first.select_option(step.value, timeout=timeout)
        return
    except Exception:
        pass
    try:
        loc.first.click(timeout=timeout)
        option = ctx.page.get_by_role("option", name=step.value)
        option.first.click(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"select failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]


def _visible_dropdown(page):
    return page.locator(
        ".el-select-dropdown:visible, "
        ".el-popper.el-select__popper:visible, "
        ".el-popper.is-pure:visible"
    )


def _click_dropdown_item(page, item: str, timeout: int | None) -> None:
    dropdown = _visible_dropdown(page)
    candidates = [
        dropdown.get_by_text(item, exact=True),
        page.get_by_role("option", name=item, exact=True),
        page.locator(".el-checkbox__label, .el-select-dropdown__item, [role='option']").filter(
            has_text=re.compile(rf"^{re.escape(item)}$")
        ),
    ]
    last_exc: Exception | None = None
    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            loc.first.click(timeout=timeout)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise StepError(
        FailureCode.BIND_ERROR,
        f"dropdown option not found: {item!r}",
        expected=item,
    ) from last_exc


def tool_multi_select(ctx: ToolContext, step: Step) -> None:
    """Element Plus checkbox multi-select: open, toggle labels, confirm if present."""
    assert step.element and step.value is not None
    values = _split_csv(step.value)
    if not values:
        raise StepError(
            FailureCode.BIND_ERROR,
            "multi_select value is empty",
            action=step.action.value,
            element=step.element,
        )
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms
    try:
        loc.first.click(timeout=timeout)
        ctx.page.wait_for_timeout(250)
        for item in values:
            _click_dropdown_item(ctx.page, item, timeout)
            ctx.page.wait_for_timeout(120)
        dropdown = _visible_dropdown(ctx.page)
        confirm = dropdown.get_by_role("button", name="确定")
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click(timeout=timeout)
        else:
            ctx.page.keyboard.press("Escape")
    except StepError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"multi_select failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_click_if_visible(ctx: ToolContext, step: Step) -> None:
    assert step.element
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms or 1500
    try:
        loc.first.wait_for(state="visible", timeout=timeout)
    except Exception:
        return
    try:
        if not loc.first.is_enabled():
            return
    except Exception:
        pass
    try:
        loc.first.click(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"click_if_visible failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_clear_select(ctx: ToolContext, step: Step) -> None:
    """Clear EP multi-select: 清空 if present, else toggle 全选 twice."""
    assert step.element
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms
    try:
        loc.first.click(timeout=timeout)
        ctx.page.wait_for_timeout(250)
        dropdown = _visible_dropdown(ctx.page)
        clearer = dropdown.get_by_text("清空", exact=True)
        if clearer.count() and clearer.first.is_visible():
            clearer.first.click(timeout=timeout)
        else:
            select_all = dropdown.get_by_text("全选", exact=True)
            if select_all.count():
                select_all.first.click(timeout=timeout)
                ctx.page.wait_for_timeout(120)
                select_all.first.click(timeout=timeout)
        confirm = dropdown.get_by_role("button", name="确定")
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click(timeout=timeout)
        else:
            ctx.page.keyboard.press("Escape")
    except StepError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"clear_select failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_hover(ctx: ToolContext, step: Step) -> None:
    assert step.element
    loc = ctx.get_locator(step.element)
    try:
        loc.first.hover(timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"hover failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_wait_visible(ctx: ToolContext, step: Step) -> None:
    assert step.element
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms or 30000
    # With live_bind: spend most of the budget on POM first; only then try alternates.
    first_timeout = max(timeout * 2 // 3, 8000) if ctx.live_bind else timeout
    first_exc: Exception | None = None
    try:
        loc.first.wait_for(state="visible", timeout=first_timeout)
        return
    except Exception as exc:  # noqa: BLE001
        first_exc = exc
    if ctx.live_bind:
        rebound = ctx._try_live_bind(step.element, exclude_current=True)
        if rebound is not None:
            try:
                resolve_locator(ctx.page, rebound).first.wait_for(
                    state="visible", timeout=min(timeout, 15000)
                )
                return
            except Exception as exc:  # noqa: BLE001
                first_exc = exc
        elif first_timeout < timeout:
            # No alternate; spend remaining budget on original locator.
            try:
                loc.first.wait_for(state="visible", timeout=timeout - first_timeout)
                return
            except Exception as exc:  # noqa: BLE001
                first_exc = exc
    raise StepError(
        FailureCode.ASSERT_FAIL,
        f"wait_visible failed: {step.element!r}: {first_exc}",
        action=step.action.value,
        element=step.element,
    )


def _validation_message_visible(page) -> bool:
    try:
        payload = page.evaluate(_VALIDATION_JS) or {}
        if any(str(x).strip() for x in (payload.get("errors") or [])):
            return True
        return bool(
            page.evaluate(
                """() => {
                  const nodes = document.querySelectorAll(
                    '.el-form-item.is-error, .el-form-item__error, .el-message--error,'
                    + ' .el-message-box, input:invalid, [aria-invalid="true"]'
                  );
                  return Array.from(nodes).some(el => {
                    const s = getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden') return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 1 && r.height > 1;
                  });
                }"""
            )
        )
    except Exception:  # noqa: BLE001
        return False


def tool_assert_visible(ctx: ToolContext, step: Step) -> None:
    assert step.element
    if step.element in {"表单校验提示", "校验提示"}:
        timeout = step.timeout_ms or 5000
        deadline = time.time() + timeout / 1000
        while True:
            if _validation_message_visible(ctx.page):
                return
            if time.time() >= deadline:
                break
            ctx.page.wait_for_timeout(200)
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "element not visible: '表单校验提示'",
            action=step.action.value,
            element=step.element,
            expected="visible",
            actual="no form-item error / error toast",
        )
    loc = ctx.get_locator(step.element)
    try:
        loc.first.wait_for(state="visible", timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"element not visible: {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected="visible",
            actual="not visible",
        ) from exc


def tool_assert_hidden(ctx: ToolContext, step: Step) -> None:
    assert step.element
    loc = ctx.get_locator(step.element)
    try:
        loc.first.wait_for(state="hidden", timeout=step.timeout_ms or 2000)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"element still visible: {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected="hidden",
            actual="visible",
        ) from exc


def tool_assert_text(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.expect is not None
    loc = ctx.get_locator(step.element)
    try:
        actual = loc.first.inner_text(timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"cannot read text of {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc
    if actual.strip() != step.expect.strip():
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"text mismatch on {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected=step.expect,
            actual=actual.strip(),
        )


_VALIDATION_JS = """() => {
  const textOf = (nodes) => Array.from(nodes)
    .filter(el => {
      const s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden') return false;
      const r = el.getBoundingClientRect();
      return r.width > 1 && r.height > 1;
    })
    .map(e => (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  const errs = textOf(document.querySelectorAll(
    '.el-form-item__error, .el-message--error, .el-notification, .el-message-box__message'
  ));
  return { errors: errs, body: (document.body && document.body.innerText || '').trim() };
}"""


def _read_assert_text(ctx: ToolContext, step: Step) -> str:
    """Prefer form/toast errors when asserting 页面 or 表单校验提示."""
    name = step.element or ""
    if name in {"页面", "当前页面", "页面正文", "表单校验提示", "校验提示"}:
        payload = ctx.page.evaluate(_VALIDATION_JS) or {}
        errors = [str(x) for x in (payload.get("errors") or []) if str(x).strip()]
        body = str(payload.get("body") or "")
        blob = "\n".join(errors)
        if step.expect and errors and step.expect in blob:
            return blob
        if name in {"表单校验提示", "校验提示"}:
            return blob or body
        return (blob + "\n" + body).strip()
    loc = ctx.get_locator(step.element)
    return loc.first.inner_text(timeout=step.timeout_ms)


def tool_assert_text_contains(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.expect is not None
    try:
        actual = _read_assert_text(ctx, step)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"cannot read text of {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc
    if step.expect not in actual:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"text not containing expected on {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected=step.expect,
            actual=actual.strip()[:2000],
        )


def tool_assert_text_not_contains(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.expect is not None
    loc = ctx.get_locator(step.element)
    try:
        actual = loc.first.inner_text(timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"cannot read text of {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc
    if step.expect in actual:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"text unexpectedly contains {step.expect!r} on {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected=f"not containing {step.expect}",
            actual=actual.strip(),
        )


def tool_assert_value(ctx: ToolContext, step: Step) -> None:
    assert step.element
    expected = step.expect if step.expect is not None else step.value
    if expected is None:
        raise StepError(FailureCode.ASSERT_FAIL, "assert_value needs expect or value")
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms or 5000
    try:
        count = min(loc.count(), 40)
    except Exception:  # noqa: BLE001
        count = 1
    actuals: list[str] = []
    # Multiple score inputs share one POM name — pass if any visible match equals expect.
    for i in range(max(count, 1)):
        item = loc.nth(i) if count else loc.first
        try:
            if count and not item.is_visible():
                continue
            actual = item.input_value(timeout=timeout if i == 0 else min(timeout, 2000))
        except Exception as exc:  # noqa: BLE001
            if i == 0 and count <= 1:
                raise StepError(
                    FailureCode.BIND_ERROR,
                    f"cannot read value of {step.element!r}: {exc}",
                    element=step.element,
                ) from exc
            continue
        actuals.append(actual)
        if actual == expected:
            return
    if not actuals:
        raise StepError(
            FailureCode.BIND_ERROR,
            f"cannot read value of {step.element!r}: no visible input",
            element=step.element,
        )
    raise StepError(
        FailureCode.ASSERT_FAIL,
        f"value mismatch on {step.element!r}",
        element=step.element,
        expected=expected,
        actual=actuals[0] if len(actuals) == 1 else ",".join(actuals[:8]),
    )


def tool_assert_url(ctx: ToolContext, step: Step) -> None:
    expected = step.expect or step.value
    assert expected is not None
    actual = ctx.page.url
    if actual != expected and actual.rstrip("/") != expected.rstrip("/"):
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "url mismatch",
            action=step.action.value,
            expected=expected,
            actual=actual,
        )


def tool_assert_url_contains(ctx: ToolContext, step: Step) -> None:
    expected = step.expect or step.value
    assert expected is not None
    actual = ctx.page.url
    if expected not in actual:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "url does not contain expected",
            action=step.action.value,
            expected=expected,
            actual=actual,
        )


def tool_assert_title(ctx: ToolContext, step: Step) -> None:
    expected = step.expect or step.value
    assert expected is not None
    actual = ctx.page.title()
    if actual != expected:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "title mismatch",
            action=step.action.value,
            expected=expected,
            actual=actual,
        )


def tool_assert_count(ctx: ToolContext, step: Step) -> None:
    assert step.element
    raw = step.expect if step.expect is not None else step.value
    assert raw is not None
    loc = ctx.get_locator(step.element)
    try:
        actual = loc.count()
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"count failed for {step.element!r}: {exc}",
            element=step.element,
        ) from exc
    if ":" in raw:
        op, args = parse_column_rule(raw)
        check_column_values([actual], op, args)
        return
    expected = int(raw)
    if actual != expected:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"count mismatch on {step.element!r}",
            element=step.element,
            expected=str(expected),
            actual=str(actual),
        )


def parse_column_rule(expect: str) -> tuple[str, list[int]]:
    raw = (expect or "").strip()
    if not raw:
        raise StepError(FailureCode.ASSERT_FAIL, "assert_column expect is empty")
    if raw.startswith("contains:") or raw.startswith("not_contains:") or raw.startswith("union:"):
        raise StepError(FailureCode.ASSERT_FAIL, f"use evaluate_column_expect for {raw}")
    if ":" in raw:
        op, rest = raw.split(":", 1)
        op = op.strip().lower()
        rest = rest.strip()
    else:
        op, rest = "eq", raw
    aliases = {"==": "eq", ">=": "gte", "<=": "lte", ">": "gt", "<": "lt", "one_of": "in"}
    op = aliases.get(op, op)
    if op not in {"eq", "gte", "lte", "gt", "lt", "in"}:
        raise StepError(FailureCode.ASSERT_FAIL, f"unsupported assert_column op: {op}")
    parts = _split_csv(rest) if op == "in" else [rest]
    nums: list[int] = []
    for part in parts:
        m = re.search(r"-?\d+", part)
        if not m:
            raise StepError(FailureCode.ASSERT_FAIL, f"assert_column expect is not numeric: {part!r}")
        nums.append(int(m.group(0)))
    return op, nums


def cell_to_int(text: str) -> int:
    m = re.search(r"-?\d+", (text or "").replace(",", "").strip())
    if not m:
        raise StepError(FailureCode.ASSERT_FAIL, f"table cell is not numeric: {text!r}")
    return int(m.group(0))


def _union_token_ok(n: int, tok: str) -> bool:
    tok = tok.strip()
    m = re.search(r"-?\d+", tok)
    if not m:
        return False
    num = int(m.group(0))
    if tok.startswith(">="):
        return n >= num
    if tok.startswith("<="):
        return n <= num
    if tok.startswith(">"):
        return n > num
    if tok.startswith("<"):
        return n < num
    return n == num


def check_column_values(values: list[int], op: str, args: list) -> None:
    if not values:
        raise StepError(FailureCode.ASSERT_FAIL, "assert_column: no data rows")
    bad: list[int] = []
    for n in values:
        ok = False
        if op == "eq":
            ok = n == args[0]
        elif op == "gte":
            ok = n >= args[0]
        elif op == "lte":
            ok = n <= args[0]
        elif op == "gt":
            ok = n > args[0]
        elif op == "lt":
            ok = n < args[0]
        elif op == "in":
            ok = n in args
        elif op == "union":
            ok = any(_union_token_ok(n, str(a)) for a in args)
        if not ok:
            bad.append(n)
    if bad:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"assert_column failed op={op} args={args} mismatches={bad[:20]}",
            expected=f"{op}:{','.join(str(a) for a in args)}",
            actual=",".join(str(v) for v in values[:30]),
        )


def _cell_contains(cell: str, needle: str) -> bool:
    text = (cell or "").strip()
    raw = (needle or "").strip()
    if not raw:
        return False
    if raw.lstrip("-").isdigit():
        try:
            return cell_to_int(text) == int(raw)
        except StepError:
            return False
    return raw in text


def evaluate_column_expect(texts: list[str], expect: str) -> None:
    raw = (expect or "").strip()
    if raw.startswith("contains:"):
        needle = raw.split(":", 1)[1]
        if not texts:
            raise StepError(FailureCode.ASSERT_FAIL, "assert_column: no data rows")
        if not any(_cell_contains(t, needle) for t in texts):
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"assert_column contains {needle!r} failed",
                expected=raw,
                actual=";".join(texts[:10]),
            )
        return
    if raw.startswith("not_contains:"):
        needle = raw.split(":", 1)[1]
        if not texts:
            raise StepError(FailureCode.ASSERT_FAIL, "assert_column: no data rows")
        bad = [t for t in texts if needle in t]
        if bad:
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"assert_column not_contains {needle!r} failed",
                expected=raw,
                actual=";".join(bad[:10]),
            )
        return
    if raw.startswith("union:"):
        tokens = _split_csv(raw.split(":", 1)[1])
        numbers = [cell_to_int(t) for t in texts]
        check_column_values(numbers, "union", tokens)
        return
    op, args = parse_column_rule(raw)
    numbers = [cell_to_int(t) for t in texts if str(t).strip()]
    check_column_values(numbers, op, args)


def _wait_table_idle(page, timeout: int) -> None:
    mask = page.locator(".el-loading-mask")
    try:
        if mask.count():
            mask.last.wait_for(state="hidden", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(400)


_TABLE_LIKE_NAMES = {
    "列表表格",
    "表格",
    "配置表",
    "获客渠道评分",
    "AI清洗评分",
    "已清洗次数评分",
    "场景维度矩阵",
    "页面",
}


def _header_matches(header: str, wanted: str) -> bool:
    h = "".join((header or "").split())
    w = "".join((wanted or "").split())
    if not h or not w:
        return False
    return h == w or w in h or h in w


def _read_tables_columns(page, *, root=None) -> list[dict]:
    """Return [{names, columns: {header: [cells]}, all_cells}] for visible tables."""
    payload = page.evaluate(
        """(root) => {
          const visible = (el) => {
            if (!el) return false;
            const s = getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 2 && r.height > 2;
          };
          const collectTables = (from) => {
            const out = [];
            const add = (t) => { if (visible(t) && !out.includes(t)) out.push(t); };
            const scope = from || document;
            if (from && (from.matches('table') || from.classList.contains('el-table'))) add(from);
            scope.querySelectorAll('table, .el-table').forEach(add);
            return out;
          };
          const tables = collectTables(root);
          return tables.map(t => {
            const names = Array.from(t.querySelectorAll(
              '.el-table__header th, thead th, tr:first-child th, th'
            )).map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim()).filter(Boolean);
            const rows = Array.from(t.querySelectorAll(
              '.el-table__body tbody tr, tbody tr'
            )).filter(r => !r.classList.contains('el-table__empty-row') && visible(r));
            const columns = {};
            const cellText = (td) => {
              if (!td) return '';
              const inp = td.querySelector('input, textarea');
              if (inp && String(inp.value || '').trim() !== '') {
                return String(inp.value).replace(/\\s+/g, ' ').trim();
              }
              return (td.innerText || '').replace(/\\s+/g, ' ').trim();
            };
            names.forEach((name, idx) => {
              columns[name] = rows.map(r => {
                const tds = r.querySelectorAll('td');
                return tds[idx] ? cellText(tds[idx]) : '';
              });
            });
            const all_cells = rows.flatMap(r => Array.from(r.querySelectorAll('td')).map(
              td => cellText(td)
            )).filter(Boolean);
            return { names, columns, all_cells };
          });
        }""",
        root,
    )
    return list(payload or [])


def _pick_column_vals(tables: list[dict], header: str, *, whole_table: bool) -> tuple[list[str], list[str]]:
    """Return (vals, tried_header_names)."""
    tried: list[str] = []
    for table in tables:
        names = [str(n) for n in (table.get("names") or [])]
        tried.extend(names)
        cols = table.get("columns") or {}
        if whole_table:
            cells = [str(c) for c in (table.get("all_cells") or [])]
            if cells:
                return cells, tried
        for name, vals in cols.items():
            if _header_matches(str(name), header):
                return [str(v) for v in (vals or [])], tried
    return [], tried


def tool_assert_column(ctx: ToolContext, step: Step) -> None:
    """Assert cells in a column (or whole table when element is a table POM)."""
    assert step.element and step.expect is not None
    timeout = step.timeout_ms or 15000
    deadline = time.time() + timeout / 1000
    texts: list[str] = []
    last_err: StepError | None = None
    whole = step.element in _TABLE_LIKE_NAMES
    while True:
        try:
            _wait_table_idle(ctx.page, min(timeout, 8000))
            root = None
            if step.element in ctx.elements:
                try:
                    loc = ctx.get_locator(step.element)
                    if loc.count() >= 1:
                        root = loc.first.element_handle()
                except Exception:  # noqa: BLE001
                    root = None
            tables = _read_tables_columns(ctx.page, root=root)
            if not tables and root is not None:
                tables = _read_tables_columns(ctx.page, root=None)
            texts, tried = _pick_column_vals(tables, step.element, whole_table=whole)
            if not texts:
                raise StepError(
                    FailureCode.BIND_ERROR,
                    f"assert_column cannot find column {step.element!r}: "
                    f"{{'error': 'header not found', 'names': {tried[:20]!r}}}",
                    element=step.element,
                )
            last_err = None
            break
        except StepError as err:
            last_err = err
        if time.time() >= deadline:
            break
        ctx.page.wait_for_timeout(400)
    if last_err is not None and not texts:
        raise last_err
    evaluate_column_expect(texts, step.expect)


def tool_assert_options(ctx: ToolContext, step: Step) -> None:
    """Open a dropdown and assert option labels (comma-separated, 全选 ignored unless listed)."""
    assert step.element and step.expect is not None
    expected = _split_csv(step.expect)
    loc = ctx.get_locator(step.element)
    timeout = step.timeout_ms
    try:
        loc.first.click(timeout=timeout)
        ctx.page.wait_for_timeout(300)
        actual = ctx.page.evaluate(
            """() => {
              const roots = Array.from(document.querySelectorAll(
                '.el-select-dropdown, .el-popper.el-select__popper, .el-popper'
              )).filter(el => {
                const s = getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && el.offsetParent !== null;
              });
              const labels = [];
              for (const root of roots) {
                root.querySelectorAll('.el-checkbox__label, [role=option], .el-select-dropdown__item')
                  .forEach(e => {
                    const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (t) labels.push(t);
                  });
              }
              return Array.from(new Set(labels));
            }"""
        )
        ctx.page.keyboard.press("Escape")
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"assert_options failed to open {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc
    actual_list = [str(x) for x in (actual or [])]
    compare_actual = [x for x in actual_list if x != "全选"] if "全选" not in expected else actual_list
    if compare_actual != expected:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"dropdown options mismatch on {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected=",".join(expected),
            actual=",".join(compare_actual),
        )


def tool_capture_column(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.value is not None
    _wait_table_idle(ctx.page, step.timeout_ms or 15000)
    texts = _read_el_table_column(ctx.page, step.element)
    ctx.vars[step.value] = texts


def _as_set(ctx: ToolContext, name: str) -> set[str]:
    if name not in ctx.vars:
        raise StepError(FailureCode.ASSERT_FAIL, f"variable not captured: {name}")
    raw = ctx.vars[name]
    if isinstance(raw, list):
        return {str(x) for x in raw if str(x).strip()}
    return {p for p in _split_csv(str(raw))}


def tool_assert_set(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.expect is not None
    _wait_table_idle(ctx.page, step.timeout_ms or 15000)
    actual = {t for t in _read_el_table_column(ctx.page, step.element) if t.strip()}
    expected = _as_set(ctx, step.expect)
    if actual != expected:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"column set mismatch vs ${{{step.expect}}}",
            element=step.element,
            expected=",".join(sorted(expected)[:20]),
            actual=",".join(sorted(actual)[:20]),
        )


def tool_assert_set_disjoint(ctx: ToolContext, step: Step) -> None:
    assert step.value and step.expect
    left = _as_set(ctx, step.value)
    right = _as_set(ctx, step.expect)
    overlap = left & right
    if overlap:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"sets {step.value} and {step.expect} overlap",
            expected="disjoint",
            actual=",".join(sorted(overlap)[:20]),
        )


_HEADER_FROM_EL_JS = """(el) => {
  const textOf = (nodes) => Array.from(nodes)
    .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim())
    .filter(Boolean);
  const fromTable = (t) => {
    if (!t) return [];
    const ths = t.querySelectorAll(
      '.el-table__header th, thead th, tr:first-child th, th'
    );
    return textOf(ths);
  };
  if (!el) return [];
  if (el.tagName === 'TABLE' || (el.classList && el.classList.contains('el-table'))) {
    return fromTable(el);
  }
  const nested = el.querySelector && el.querySelector('table, .el-table');
  if (nested) return fromTable(nested);
  const closest = el.closest && (el.closest('table') || el.closest('.el-table'));
  if (closest) return fromTable(closest);
  // Section title / label: prefer a following table in nearby ancestors.
  let root = el.parentElement;
  for (let d = 0; d < 5 && root; d++, root = root.parentElement) {
    const tables = root.querySelectorAll('table, .el-table');
    for (const t of tables) {
      if (el.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING) {
        const hs = fromTable(t);
        if (hs.length) return hs;
      }
    }
  }
  return textOf(el.querySelectorAll('th, .el-table__header th'));
}"""


def _match_headers(headers: list[str], wanted: list[str]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    unexpected: list[str] = []
    for item in wanted:
        if item.startswith("!"):
            name = item[1:]
            if any(_header_matches(h, name) for h in headers):
                unexpected.append(name)
        elif not any(_header_matches(h, item) for h in headers):
            missing.append(item)
    return missing, unexpected


def tool_assert_headers(ctx: ToolContext, step: Step) -> None:
    """Assert expected headers exist in the table scoped by step.element when set."""
    assert step.expect is not None
    wanted = _split_csv(step.expect)
    candidates: list[list[str]] = []

    if step.element:
        loc = ctx.get_locator(step.element)
        try:
            count = min(loc.count(), 40)
        except Exception:  # noqa: BLE001
            count = 0
        for i in range(count):
            try:
                item = loc.nth(i)
                if not item.is_visible():
                    continue
                raw = item.evaluate(_HEADER_FROM_EL_JS)
                headers = [str(h) for h in (raw or [])]
                if headers:
                    candidates.append(headers)
            except Exception:  # noqa: BLE001
                continue

    if not candidates:
        # Fallback: page-wide (el-table + native tables), for legacy steps without element.
        raw = ctx.page.evaluate(
            """() => {
              const textOf = (nodes) => Array.from(nodes)
                .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim())
                .filter(Boolean);
              const out = [];
              document.querySelectorAll('.el-table, table').forEach(t => {
                const hs = textOf(t.querySelectorAll(
                  '.el-table__header th, thead th, tr:first-child th, th'
                ));
                if (hs.length) out.push(hs);
              });
              return out;
            }"""
        )
        for hs in raw or []:
            candidates.append([str(h) for h in hs])

    if not candidates:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "table headers mismatch: no table headers found",
            expected=step.expect,
            actual="",
            element=step.element,
        )

    best_headers: list[str] = candidates[0]
    best_missing, best_unexpected = _match_headers(best_headers, wanted)
    for headers in candidates:
        missing, unexpected = _match_headers(headers, wanted)
        if not missing and not unexpected:
            return
        if len(missing) + len(unexpected) < len(best_missing) + len(best_unexpected):
            best_headers, best_missing, best_unexpected = headers, missing, unexpected

    raise StepError(
        FailureCode.ASSERT_FAIL,
        f"table headers mismatch missing={best_missing} unexpected={best_unexpected}",
        expected=step.expect,
        actual=",".join(best_headers),
        element=step.element,
    )


def tool_assert_filter_order(ctx: ToolContext, step: Step) -> None:
    assert step.expect is not None
    wanted = _split_csv(step.expect)
    labels = ctx.page.evaluate(
        """() => {
          const btn = Array.from(document.querySelectorAll('button')).find(
            b => (b.innerText || '').replace(/\\s+/g,'').includes('查询')
          );
          const root = btn ? (btn.closest('form') || btn.parentElement?.parentElement?.parentElement || document.body) : document.body;
          const out = [];
          for (const el of root.querySelectorAll('*')) {
            if (el.closest('.el-table')) continue;
            const t = (el.childNodes.length && el.childNodes[0].nodeType === 3)
              ? el.childNodes[0].textContent.replace(/\\s+/g,' ').trim()
              : '';
            if (t && t.length >= 2 && t.length <= 8 && !out.includes(t)) out.push(t);
          }
          return out;
        }"""
    )
    labels = [str(x) for x in (labels or [])]
    idxs = []
    for name in wanted:
        try:
            idxs.append(labels.index(name))
        except ValueError:
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"filter label not found: {name}",
                expected=step.expect,
                actual=",".join(labels),
            ) from None
    if idxs != sorted(idxs):
        raise StepError(
            FailureCode.ASSERT_FAIL,
            "filter labels are not in expected left-to-right order",
            expected=step.expect,
            actual=",".join(labels),
        )


ACTION_TOOLS = {
    ActionName.open: tool_open,
    ActionName.click: tool_click,
    ActionName.click_if_visible: tool_click_if_visible,
    ActionName.fill: tool_fill,
    ActionName.select: tool_select,
    ActionName.multi_select: tool_multi_select,
    ActionName.clear_select: tool_clear_select,
    ActionName.hover: tool_hover,
    ActionName.wait_visible: tool_wait_visible,
    ActionName.assert_visible: tool_assert_visible,
    ActionName.assert_hidden: tool_assert_hidden,
    ActionName.assert_text: tool_assert_text,
    ActionName.assert_text_contains: tool_assert_text_contains,
    ActionName.assert_text_not_contains: tool_assert_text_not_contains,
    ActionName.assert_value: tool_assert_value,
    ActionName.assert_url: tool_assert_url,
    ActionName.assert_url_contains: tool_assert_url_contains,
    ActionName.assert_title: tool_assert_title,
    ActionName.assert_count: tool_assert_count,
    ActionName.assert_column: tool_assert_column,
    ActionName.assert_options: tool_assert_options,
    ActionName.capture_column: tool_capture_column,
    ActionName.assert_set: tool_assert_set,
    ActionName.assert_set_disjoint: tool_assert_set_disjoint,
    ActionName.assert_headers: tool_assert_headers,
    ActionName.assert_filter_order: tool_assert_filter_order,
}


def apply_navigation_observe(ctx: ToolContext, nav: NavigationObserve, *, timeout_ms: int) -> None:
    if nav.expect_url:
        try:
            ctx.page.wait_for_url(nav.expect_url, timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"navigation expect_url failed: {nav.expect_url}",
                expected=nav.expect_url,
                actual=ctx.page.url,
            ) from exc
    if nav.expect_url_contains:
        pattern = re.compile(".*" + re.escape(nav.expect_url_contains) + ".*")
        try:
            ctx.page.wait_for_url(pattern, timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"navigation expect_url_contains failed: {nav.expect_url_contains}",
                expected=nav.expect_url_contains,
                actual=ctx.page.url,
            ) from exc
    if nav.expect_element:
        loc = ctx.get_locator(nav.expect_element)
        try:
            loc.first.wait_for(state="visible", timeout=timeout_ms)
        except Exception as exc:  # noqa: BLE001
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"navigation expect_element not visible: {nav.expect_element}",
                element=nav.expect_element,
            ) from exc


def apply_observe(ctx: ToolContext, observe: ObserveSpec | None) -> None:
    """Phase 1: navigation observe only. Toast observe deferred to Phase 3."""
    if observe is None:
        return
    if observe.toasts or observe.forbid_toast_levels:
        # Schema accepts toast rules; runtime not ready until Phase 3.
        pass
    if observe.navigation:
        apply_navigation_observe(ctx, observe.navigation, timeout_ms=observe.window_ms)


def interpolate_step(ctx: ToolContext, step: Step) -> Step:
    pattern = re.compile(r"\$\{([^}]+)\}")

    def repl(text: str | None) -> str | None:
        if text is None:
            return None

        def one(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in ctx.vars:
                raise StepError(FailureCode.ASSERT_FAIL, f"unresolved variable ${{{key}}}")
            val = ctx.vars[key]
            if isinstance(val, list):
                return val[0] if val else ""
            return str(val)

        return pattern.sub(one, text)

    return step.model_copy(update={"value": repl(step.value), "expect": repl(step.expect), "url": repl(step.url)})


def run_action(ctx: ToolContext, step: Step) -> None:
    step = interpolate_step(ctx, step)
    fn = ACTION_TOOLS.get(step.action)
    if fn is None:
        raise StepError(
            FailureCode.NEEDS_REVIEW,
            f"unsupported action: {step.action}",
            action=getattr(step.action, "value", str(step.action)),
        )
    fn(ctx, step)
