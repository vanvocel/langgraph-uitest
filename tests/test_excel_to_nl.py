from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from framework.agents.excel_nl.graph import run_excel_nl_graph
from framework.agents.excel_nl.service import _detect_skip, excel_to_nl_requirement, render_nl
from framework.agents.excel_nl.config import ExcelToNlConfig
from framework.agents.pipeline.graph import build_ingest_compile_graph


def _write_sample_excel(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["需求标题"])
    ws.append(
        [
            "钉钉需求编号",
            "模块",
            "用例ID",
            "用例标题",
            "前置条件",
            "测试步骤",
            "预期结果",
            "测试结果",
            "测试截图",
            "测试说明",
        ]
    )
    ws.append(
        [
            "DEMO",
            "模块A",
            "TC-DEMO-001",
            "打开页面可见按钮",
            "已登录",
            "1. 打开页面\n2. 点击查询",
            "展示结果列表",
            None,
            None,
            "",
        ]
    )
    ws.append(
        [
            "DEMO",
            "模块A",
            "TC-DEMO-002",
            "AI外呼结果回写",
            "依赖外呼",
            "1. 触发外呼",
            "回写成功",
            None,
            None,
            "【人工/AI外呼】",
        ]
    )
    ws.append(
        [
            "DEMO",
            "模块A",
            "TC-DEMO-003",
            "需造数场景",
            "需要预置客资",
            "1. 造数后打开页",
            "可见数据",
            None,
            None,
            "跨模块造数",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def test_detect_skip_from_note_and_keywords():
    cfg = ExcelToNlConfig()
    assert (
        _detect_skip(
            case_id="A",
            title="t",
            pre="",
            steps="",
            expect="",
            note="【人工/AI外呼】",
            cfg=cfg,
        )
        == "ai_outbound"
    )
    assert (
        _detect_skip(
            case_id="B",
            title="需造数校验",
            pre="",
            steps="",
            expect="",
            note="",
            cfg=cfg,
        )
        == "needs_fixture"
    )


def test_render_nl_contains_page_and_skip_banner():
    cfg = ExcelToNlConfig(page_url="https://example.com/x", tab="页签A", account_ref="default_tester")
    text = render_nl(
        case_id="TC-1",
        title="标题",
        pre="已登录",
        steps="1. 点查询",
        expect="有结果",
        cfg=cfg,
        skip="needs_fixture",
    )
    assert "【需造数】" in text
    assert "https://example.com/x" in text
    assert "页签A" in text
    assert "1. 点查询" in text


def test_excel_to_nl_requirement_writes_files(tmp_path: Path, monkeypatch):
    req = "EXCEL-NL-DEMO"
    runs = tmp_path / "runs" / req
    excel = runs / "excel" / "cases.xlsx"
    _write_sample_excel(excel)
    monkeypatch.setattr("framework.agents.excel_nl.service.req_dir", lambda rid: runs)
    monkeypatch.setattr("framework.agents.excel_nl.config.req_dir", lambda rid: runs)
    monkeypatch.setattr("framework.agents.excel_nl.service.init_requirement", lambda rid: runs)
    monkeypatch.setattr(
        "framework.agents.excel_nl.service.resolve_source_excel",
        lambda *a, **k: excel,
    )
    (runs / "excel_nl.yaml").write_text(
        'page_url: "https://demo.example/clean/"\ntab: "清洗评分规则"\n',
        encoding="utf-8",
    )
    report = excel_to_nl_requirement(req)
    assert report["ok"] is True
    assert report["count"] == 3
    nl1 = (runs / "nl" / "TC-DEMO-001.nl.md").read_text(encoding="utf-8")
    assert "打开页面可见按钮" in nl1
    assert "https://demo.example/clean/" in nl1
    nl2 = (runs / "nl" / "TC-DEMO-002.nl.md").read_text(encoding="utf-8")
    assert "【人工/AI外呼】" in nl2
    nl3 = (runs / "nl" / "TC-DEMO-003.nl.md").read_text(encoding="utf-8")
    assert "【需造数】" in nl3


def test_excel_nl_langgraph_and_pipeline_graph_build():
    g = build_ingest_compile_graph()
    assert g is not None
    # Graph invoke with missing excel should record error, not crash
    state = run_excel_nl_graph("NO-SUCH-REQ-FOR-GRAPH")
    assert state.get("errors")
