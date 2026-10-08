"""Phase 4 compile skeleton (stub backend, no API key)."""

from __future__ import annotations

from pathlib import Path

from framework.agents.compile.graph import compile_nl, normalize_compiled
from framework.llm.profiles import resolve_profile
from framework.schema.case import UiCase


def test_resolve_default_profile():
    p = resolve_profile()
    assert p.name == "deepseek"
    assert p.api_key_env == "DEEPSEEK_API_KEY"
    assert p.base_url.startswith("https://")


def test_resolve_named_profiles():
    assert resolve_profile("zhipu").api_key_env == "ZHIPUAI_API_KEY"
    assert resolve_profile("gpt").model


def test_stub_compile_frozen_org():
    nl = "期望弹出错误 toast，完整文案为：账号已冻结，请先联系管理员。"
    state = compile_nl(nl, req_id="TOAST-LIVE", force_backend="stub")
    assert not state["errors"]
    assert state["backend"] == "stub"
    case = UiCase.model_validate(state["yaml_case"])
    click = [s for s in case.steps if s.action.value == "click"][-1]
    assert click.observe and click.observe.toasts
    assert click.observe.toasts[0].contains == "账号已冻结，请先联系管理员"


def test_stub_unknown_marks_review():
    state = compile_nl("随便点一下不知道的页面", req_id="X", force_backend="stub")
    assert state["needs_review"] is True
    UiCase.model_validate(state["yaml_case"])


def test_stub_compile_mg0473_options():
    nl = Path("runs/MG0473/nl/TC-MG0473-001.nl.md").read_text(encoding="utf-8")
    state = compile_nl(nl, req_id="MG0473", force_backend="stub")
    assert not state["errors"]
    case = UiCase.model_validate(state["yaml_case"])
    assert case.case_id == "TC-MG0473-001"
    opts = [s for s in case.steps if s.action.value == "assert_options"]
    assert opts and "三次及以上" in (opts[0].expect or "")


def test_normalize_compiled_headers_and_aliases():
    raw = {
        "case_id": "X",
        "title": "t",
        "requirement_id": "MG0473",
        "steps": [
            {"action": "multi_select", "element": "清洗次数", "value": "未清洗,首次清洗"},
            {"action": "assert_text_contains", "element": "触发器", "expect": "+ 1"},
            {"action": "assert_headers", "expect": "清洗次数,!清洗状态"},
            {"action": "click", "element": "关闭弹窗"},
        ],
        "meta": {"needs_review": True, "review_notes": "触发器文案未明确"},
    }
    out = normalize_compiled(raw)
    assert out["steps"][1]["element"] == "清洗次数"
    assert out["steps"][2]["element"] == "列表表格"
    assert out["steps"][3]["element"] == "弹窗关闭"
    assert out["meta"]["needs_review"] is False
    UiCase.model_validate(out)
