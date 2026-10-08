"""Basic UI action and assertion tools (no LLM)."""

from __future__ import annotations

import re
import time
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
    ) -> None:
        self.page = page
        self.elements = elements
        self.base_url = (base_url or "").rstrip("/")
        self.fixture_dir = fixture_dir
        self.vars: dict[str, list[str] | str] = {}

    def get_locator(self, element_name: str):
        loc_def = self.elements.get(element_name)
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
    try:
        loc.first.click(timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        try:
            loc.first.click(timeout=step.timeout_ms or 5000, force=True)
            return
        except Exception:
            pass
        raise StepError(
            FailureCode.BIND_ERROR,
            f"click failed on {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_fill(ctx: ToolContext, step: Step) -> None:
    assert step.element and step.value is not None
    loc = ctx.get_locator(step.element)
    try:
        loc.first.fill(step.value, timeout=step.timeout_ms)
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
    try:
        loc.first.wait_for(state="visible", timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"wait_visible failed: {step.element!r}: {exc}",
            action=step.action.value,
            element=step.element,
        ) from exc


def tool_assert_visible(ctx: ToolContext, step: Step) -> None:
    assert step.element
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


def tool_assert_text_contains(ctx: ToolContext, step: Step) -> None:
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
    if step.expect not in actual:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"text not containing expected on {step.element!r}",
            action=step.action.value,
            element=step.element,
            expected=step.expect,
            actual=actual.strip(),
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
    try:
        actual = loc.first.input_value(timeout=step.timeout_ms)
    except Exception as exc:  # noqa: BLE001
        raise StepError(
            FailureCode.BIND_ERROR,
            f"cannot read value of {step.element!r}: {exc}",
            element=step.element,
        ) from exc
    if actual != expected:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"value mismatch on {step.element!r}",
            element=step.element,
            expected=expected,
            actual=actual,
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


def evaluate_column_expect(texts: list[str], expect: str) -> None:
    raw = (expect or "").strip()
    if raw.startswith("contains:"):
        needle = raw.split(":", 1)[1]
        if not texts:
            raise StepError(FailureCode.ASSERT_FAIL, "assert_column: no data rows")
        bad = [t for t in texts if needle not in t]
        if bad:
            raise StepError(
                FailureCode.ASSERT_FAIL,
                f"assert_column contains {needle!r} failed",
                expected=raw,
                actual=";".join(bad[:10]),
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
    numbers = [cell_to_int(t) for t in texts]
    check_column_values(numbers, op, args)


def _wait_table_idle(page, timeout: int) -> None:
    mask = page.locator(".el-loading-mask")
    try:
        if mask.count():
            mask.last.wait_for(state="hidden", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(400)


def _read_el_table_column(page, header: str) -> list[str]:
    payload = page.evaluate(
        """(header) => {
          const tables = Array.from(document.querySelectorAll('.el-table')).filter(t => t.offsetParent !== null);
          const table = tables[0];
          if (!table) return { error: 'no table' };
          const names = Array.from(table.querySelectorAll('.el-table__header th'))
            .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim());
          const idx = names.findIndex(n => n === header || n.includes(header));
          if (idx < 0) return { error: 'header not found', names };
          const rows = Array.from(table.querySelectorAll('.el-table__body tbody tr'))
            .filter(r => !r.classList.contains('el-table__empty-row'));
          const vals = rows.map(r => {
            const tds = r.querySelectorAll('td');
            return tds[idx] ? (tds[idx].innerText || '').replace(/\\s+/g, ' ').trim() : '';
          });
          return { names, idx, vals };
        }""",
        header,
    )
    if payload.get("error"):
        raise StepError(
            FailureCode.BIND_ERROR,
            f"assert_column cannot find column {header!r}: {payload}",
            element=header,
        )
    return list(payload.get("vals") or [])


def tool_assert_column(ctx: ToolContext, step: Step) -> None:
    """Assert every visible-page cell in a named table column matches expect."""
    assert step.element and step.expect is not None
    timeout = step.timeout_ms or 15000
    deadline = time.time() + timeout / 1000
    texts: list[str] = []
    last_err: StepError | None = None
    while True:
        try:
            _wait_table_idle(ctx.page, min(timeout, 8000))
            texts = _read_el_table_column(ctx.page, step.element)
            last_err = None
            if texts:
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


def tool_assert_headers(ctx: ToolContext, step: Step) -> None:
    assert step.expect is not None
    headers = ctx.page.evaluate(
        """() => Array.from(document.querySelectorAll('.el-table__header th'))
          .map(e => (e.innerText||'').replace(/\\s+/g,' ').trim()).filter(Boolean)"""
    )
    headers = [str(h) for h in (headers or [])]
    wanted = _split_csv(step.expect)
    missing = []
    unexpected = []
    for item in wanted:
        if item.startswith("!"):
            name = item[1:]
            if name in headers:
                unexpected.append(name)
        elif item not in headers:
            missing.append(item)
    if missing or unexpected:
        raise StepError(
            FailureCode.ASSERT_FAIL,
            f"table headers mismatch missing={missing} unexpected={unexpected}",
            expected=step.expect,
            actual=",".join(headers),
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
