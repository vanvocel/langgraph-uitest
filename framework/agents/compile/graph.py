"""NL → YAML LangGraph (Phase 4). Default backend is stub (no remote LLM)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from framework.agents.compile.lint import lint_compiled
from framework.agents.compile.prompt import SYSTEM_PROMPT
from framework.agents.compile.stub import stub_compile
from framework.llm.profiles import LlmProfile, compile_backend, resolve_profile
from framework.schema.case import UiCase


class CompileState(TypedDict, total=False):
    nl_text: str
    nl_path: str
    req_id: str
    llm_profile: str
    yaml_case: dict[str, Any]
    errors: list[str]
    needs_review: bool
    backend: str
    force_backend: str


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def _llm_compile(
    nl_text: str,
    req_id: str,
    profile: LlmProfile,
    *,
    suggested_case_id: str = "",
) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=profile.model,
        api_key=profile.api_key,
        base_url=profile.base_url,
        temperature=profile.temperature,
    )
    hint = f"建议 case_id={suggested_case_id}\n" if suggested_case_id else ""
    human = (
        f"requirement_id={req_id}\n"
        f"{hint}\n"
        f"自然语言用例：\n{nl_text}\n\n"
        "请只输出一个 JSON 对象，不要 markdown。"
    )
    result = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human)])
    content = result.content if hasattr(result, "content") else str(result)
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    data = _extract_json(str(content))
    data["requirement_id"] = data.get("requirement_id") or req_id
    meta = dict(data.get("meta") or {})
    meta.setdefault("compile_backend", profile.name)
    data["meta"] = meta
    return data


_ELEMENT_ALIASES = {
    "关闭弹窗": "弹窗关闭",
    "关闭": "弹窗关闭",
    "弹窗关闭按钮": "弹窗关闭",
}


def normalize_compiled(raw: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM slips so UiCase validation and POM names line up."""
    steps = raw.get("steps") or []
    last_select: str | None = None
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "")
        element = step.get("element")
        if isinstance(element, str):
            element = element.strip()
            if element in _ELEMENT_ALIASES:
                element = _ELEMENT_ALIASES[element]
            if element in {"触发器", "下拉触发器"} and last_select:
                element = last_select
            step["element"] = element or None
        if action in {"multi_select", "select"} and step.get("element"):
            last_select = str(step["element"])
        if action == "assert_headers" and not step.get("element"):
            step["element"] = "列表表格"
        if action == "assert_column" and not step.get("element"):
            step["element"] = last_select or "清洗次数"
        if action == "assert_column" and step.get("expect") is None:
            # LLM sometimes puts expect under contains / column / value
            step["expect"] = (
                step.get("contains")
                or step.get("column")
                or step.get("value")
                or step.get("expected")
            )
        if action in {"assert_text_contains", "assert_text"} and not step.get("element") and last_select:
            step["element"] = last_select
        if action == "capture_column" and not step.get("value"):
            step["value"] = (
                step.get("variable")
                or step.get("var")
                or step.get("name")
                or step.get("as")
                or step.get("expect")
            )
            if not step.get("value") and step.get("element"):
                # last resort: derive a safe variable name from element
                el = str(step["element"]).strip()
                step["value"] = f"col_{el}" if el else "col_value"
        if action == "assert_set" and not step.get("expect"):
            step["expect"] = (
                step.get("target_var")
                or step.get("variable")
                or step.get("var")
                or step.get("expect_var")
            )
        if action in {"capture_column", "assert_set"} and step.get("element") == "列表表格":
            step["element"] = "线索 ID"
        # drop unsupported precondition-like keys that break nothing but clean steps
        for junk in ("contains", "column", "variable", "var", "name", "as", "expected", "target_var", "expect_var"):
            if junk in step and junk not in {"value"}:
                # keep if still needed as expect already copied
                if action == "assert_column" and junk in {"contains", "column", "value", "expected"}:
                    step.pop(junk, None)
                elif action == "capture_column" and junk in {"variable", "var", "name", "as", "expect"}:
                    step.pop(junk, None)
    meta = dict(raw.get("meta") or {})
    notes = str(meta.get("review_notes") or "")
    if "触发器" in notes and meta.get("needs_review"):
        meta["needs_review"] = False
        meta.pop("review_notes", None)
        raw["meta"] = meta
    return raw


def _use_llm(profile: LlmProfile, force: str) -> bool:
    mode = (force or compile_backend()).lower()
    if mode == "stub":
        return False
    if mode == "llm":
        if not profile.has_key:
            raise ValueError(f"backend=llm but {profile.api_key_env} is empty")
        return True
    return profile.has_key


def node_parse(state: CompileState) -> CompileState:
    errors = list(state.get("errors") or [])
    req_id = state["req_id"]
    nl_text = state["nl_text"]
    profile = resolve_profile(state.get("llm_profile") or None)
    try:
        if _use_llm(profile, state.get("force_backend") or ""):
            stem = Path(state.get("nl_path") or "").name
            for suf in (".nl.md", ".md", ".txt", ".nl"):
                if stem.lower().endswith(suf):
                    stem = stem[: -len(suf)]
                    break
            raw = _llm_compile(nl_text, req_id, profile, suggested_case_id=stem)
            backend = profile.name
        else:
            raw = stub_compile(nl_text, req_id)
            backend = "stub"
        if not isinstance(raw, dict):
            raise ValueError("compile output is not an object")
        raw = normalize_compiled(raw)
        raw, _lint_notes = lint_compiled(raw, nl_text)
        case = UiCase.model_validate(raw)
        meta = dict(case.meta or {})
        meta["compile_backend"] = backend
        meta["llm_profile"] = profile.name
        needs = bool(meta.get("needs_review"))
        case.meta = meta
        return {
            "yaml_case": case.model_dump(mode="json", exclude_none=True),
            "errors": errors,
            "needs_review": needs,
            "backend": backend,
        }
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        return {
            "yaml_case": {},
            "errors": errors,
            "needs_review": True,
            "backend": "error",
        }


def node_gate(state: CompileState) -> CompileState:
    """If schema produced a case but parser is uncertain, keep needs_review."""
    case = state.get("yaml_case") or {}
    meta = dict(case.get("meta") or {})
    if state.get("backend") == "error" or not case:
        return {"needs_review": True}
    if meta.get("needs_review"):
        return {"needs_review": True}
    return {"needs_review": bool(state.get("needs_review"))}


def build_compile_graph():
    g = StateGraph(CompileState)
    g.add_node("parse_to_yaml", node_parse)
    g.add_node("gate_review", node_gate)
    g.add_edge(START, "parse_to_yaml")
    g.add_edge("parse_to_yaml", "gate_review")
    g.add_edge("gate_review", END)
    return g.compile()


_APP = None


def compile_nl(
    nl_text: str,
    *,
    req_id: str,
    nl_path: str = "",
    llm_profile: str | None = None,
    force_backend: str = "",
) -> CompileState:
    global _APP
    if _APP is None:
        _APP = build_compile_graph()
    return _APP.invoke(
        {
            "nl_text": nl_text,
            "nl_path": nl_path,
            "req_id": req_id,
            "llm_profile": llm_profile or "",
            "force_backend": force_backend,
            "yaml_case": {},
            "errors": [],
            "needs_review": False,
            "backend": "",
        }
    )
