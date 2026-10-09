"""LangGraph: Excel → NL (deterministic, no LLM)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from framework.agents.excel_nl.service import excel_to_nl_requirement


class ExcelNlState(TypedDict, total=False):
    req_id: str
    excel: str
    page_url: str
    tab: str
    report: dict[str, Any]
    errors: list[str]


def node_excel_to_nl(state: ExcelNlState) -> ExcelNlState:
    errors = list(state.get("errors") or [])
    try:
        report = excel_to_nl_requirement(
            state["req_id"],
            excel=state.get("excel") or None,
            page_url=state.get("page_url") or None,
            tab=state.get("tab") or None,
        )
        return {"report": report, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
        return {"report": {"ok": False}, "errors": errors}


def build_excel_nl_graph():
    g = StateGraph(ExcelNlState)
    g.add_node("excel_to_nl", node_excel_to_nl)
    g.add_edge(START, "excel_to_nl")
    g.add_edge("excel_to_nl", END)
    return g.compile()


_APP = None


def run_excel_nl_graph(
    req_id: str,
    *,
    excel: str | None = None,
    page_url: str | None = None,
    tab: str | None = None,
) -> ExcelNlState:
    global _APP
    if _APP is None:
        _APP = build_excel_nl_graph()
    return _APP.invoke(
        {
            "req_id": req_id,
            "excel": excel or "",
            "page_url": page_url or "",
            "tab": tab or "",
            "report": {},
            "errors": [],
        }
    )
