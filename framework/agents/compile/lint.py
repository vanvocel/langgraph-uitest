"""Deterministic post-compile fixes so LLM YAML does not assert on 页面."""

from __future__ import annotations

from typing import Any

_PAGE_NAMES = {"页面", "当前页面", "页面正文", "body"}
_GENERIC_SCORE = {"得分输入框", "渠道得分"}
_SUCCESS_MARKERS = ("保存成功",)
_SCORE_TABLES = (
    ("获客渠道评分", "获客渠道得分输入框"),
    ("AI清洗评分", "AI清洗得分输入框"),
    ("AI外呼评分", "AI清洗得分输入框"),
    ("已清洗次数评分", "已清洗次数得分输入框"),
)
_HEADER_TABLES = (
    "获客渠道评分",
    "AI清洗评分",
    "已清洗次数评分",
    "场景维度矩阵",
)


def _expect_body(nl_text: str) -> str:
    text = nl_text or ""
    for key in ("预期：", "预期:", "预期"):
        idx = text.find(key)
        if idx >= 0:
            return text[idx:]
    return text


def _score_input_for_nl(nl_text: str) -> str | None:
    text = nl_text or ""
    head = text.split("\n", 1)[0]
    for title, element in _SCORE_TABLES:
        if title in head:
            return element
    for title, element in _SCORE_TABLES:
        if title in text:
            return element
    return None


def _header_table_for_nl(nl_text: str) -> str | None:
    text = nl_text or ""
    head = text.split("\n", 1)[0]
    for name in _HEADER_TABLES:
        if name in head:
            return name
    for name in _HEADER_TABLES:
        if name in text:
            return name
    return None


def _allow_error_on_prev_save(out: list[dict[str, Any]]) -> None:
    for prev in reversed(out):
        if prev.get("action") == "click" and prev.get("element") in {"保存", "确定", "确认"}:
            obs = dict(prev.get("observe") or {})
            obs["forbid_toast_levels"] = []
            prev["observe"] = obs
            return


def lint_compiled(raw: dict[str, Any], nl_text: str = "") -> tuple[dict[str, Any], list[str]]:
    """Rewrite unsafe LLM steps. Returns (case, lint notes)."""
    issues: list[str] = []
    steps = raw.get("steps") or []
    if not isinstance(steps, list):
        return raw, issues
    expect_nl = _expect_body(nl_text)
    score_el = _score_input_for_nl(nl_text)
    header_el = _header_table_for_nl(nl_text)
    out: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            out.append(step)
            continue
        step = dict(step)
        action = str(step.get("action") or "")
        element = step.get("element")
        if isinstance(element, str):
            element = element.strip()
            step["element"] = element
        expect = step.get("expect")
        expect_s = str(expect).strip() if expect is not None else ""

        if action == "fill" and element in _GENERIC_SCORE and score_el:
            step["element"] = score_el
            issues.append(f"fill {element} → {score_el}")
            out.append(step)
            continue

        if action == "assert_headers" and element == "列表表格" and header_el:
            step["element"] = header_el
            issues.append(f"assert_headers 列表表格 → {header_el}")
            out.append(step)
            continue

        if action in {"assert_text_contains", "assert_text"} and element in _PAGE_NAMES:
            if any(m in expect_s for m in _SUCCESS_MARKERS):
                step["action"] = "assert_visible"
                step["element"] = "保存成功"
                step.pop("expect", None)
                issues.append("assert 页面/保存成功 → assert_visible 保存成功")
            elif expect_s and expect_s in expect_nl:
                step["element"] = "表单校验提示"
                _allow_error_on_prev_save(out)
                issues.append(f"assert 页面/{expect_s} → 表单校验提示")
            else:
                step["action"] = "assert_visible"
                step["element"] = "表单校验提示"
                step.pop("expect", None)
                _allow_error_on_prev_save(out)
                issues.append("assert 页面(无预期原文) → assert_visible 表单校验提示")
            out.append(step)
            continue

        if action == "assert_visible" and element in _PAGE_NAMES:
            step["element"] = "保存成功"
            issues.append("assert_visible 页面 → 保存成功")
            out.append(step)
            continue

        out.append(step)

    raw = dict(raw)
    raw["steps"] = out
    if issues:
        meta = dict(raw.get("meta") or {})
        notes = [str(meta.get("review_notes") or "").strip(), "compile_lint: " + "; ".join(issues)]
        meta["compile_lint"] = issues
        meta["review_notes"] = " ".join(x for x in notes if x).strip()
        raw["meta"] = meta
    return raw, issues
