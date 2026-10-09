"""LangGraph pipeline: excel_to_nl → compile (NL→YAML via existing compile graph)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from framework.agents.compile.service import compile_requirement
from framework.agents.excel_nl.service import excel_to_nl_requirement


class PipelineState(TypedDict, total=False):
    req_id: str
    excel: str
    page_url: str
    tab: str
    llm_profile: str
    force_backend: str
    from_excel: bool
    excel_report: dict[str, Any]
    compile_results: list[dict[str, Any]]
    errors: list[str]


def node_excel_to_nl(state: PipelineState) -> PipelineState:
    if not state.get("from_excel", True):
        return {"excel_report": {"ok": True, "skipped": True}}
    errors = list(state.get("errors") or [])
    try:
        report = excel_to_nl_requirement(
            state["req_id"],
            excel=state.get("excel") or None,
            page_url=state.get("page_url") or None,
            tab=state.get("tab") or None,
        )
        return {"excel_report": report, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"excel_to_nl: {exc}")
        return {"excel_report": {"ok": False}, "errors": errors}


def node_compile(state: PipelineState) -> PipelineState:
    errors = list(state.get("errors") or [])
    if errors and not (state.get("excel_report") or {}).get("ok", True):
        return {"compile_results": [], "errors": errors}
    try:
        results = compile_requirement(
            state["req_id"],
            llm_profile=state.get("llm_profile") or None,
            force_backend=state.get("force_backend") or "",
        )
        return {"compile_results": results, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"compile: {exc}")
        return {"compile_results": [], "errors": errors}


def build_ingest_compile_graph():
    g = StateGraph(PipelineState)
    g.add_node("excel_to_nl", node_excel_to_nl)
    g.add_node("compile", node_compile)
    g.add_edge(START, "excel_to_nl")
    g.add_edge("excel_to_nl", "compile")
    g.add_edge("compile", END)
    return g.compile()


_APP = None


def run_ingest_compile_pipeline(
    req_id: str,
    *,
    excel: str | None = None,
    page_url: str | None = None,
    tab: str | None = None,
    llm_profile: str | None = None,
    force_backend: str = "",
    from_excel: bool = True,
) -> PipelineState:
    """Excel→NL then NL→YAML in one LangGraph run."""
    global _APP
    if _APP is None:
        _APP = build_ingest_compile_graph()
    return _APP.invoke(
        {
            "req_id": req_id,
            "excel": excel or "",
            "page_url": page_url or "",
            "tab": tab or "",
            "llm_profile": llm_profile or "",
            "force_backend": force_backend,
            "from_excel": from_excel,
            "excel_report": {},
            "compile_results": [],
            "errors": [],
        }
    )
