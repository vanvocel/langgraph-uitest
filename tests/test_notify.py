from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from framework.notify.channels.feishu import FeishuChannel, _feishu_file_type
from framework.notify.models import ReportPayload
from framework.notify.registry import create_channel, known_channels
from framework.notify.service import build_report_payload, notify_report


def test_known_channels_include_feishu_email_wecom():
    names = known_channels()
    assert "feishu" in names
    assert "email" in names
    assert "wecom" in names


def test_report_payload_summary_and_attachments(tmp_path: Path):
    excel = tmp_path / "a.xlsx"
    html = tmp_path / "r.html"
    excel.write_bytes(b"x")
    html.write_text("<html></html>", encoding="utf-8")
    payload = ReportPayload(
        req_id="MG0557",
        title="MG0557 UI",
        passed=4,
        failed=2,
        blocked=3,
        excel_path=excel,
        html_path=html,
        failed_cases=["TC-A", "TC-B"],
    )
    text = payload.summary_text()
    assert "通过：4" in text
    assert "失败：2" in text
    assert "TC-A" in text
    assert payload.has_failure
    assert len(payload.attachment_paths()) == 2

    with_url = ReportPayload(
        req_id="MG0557",
        title="MG0557 UI",
        excel_path=excel,
        html_path=html,
        report_url="https://uitest.example.com/reports/MG0557/allure-report.html",
    )
    assert "报告链接：" in with_url.summary_text()
    # URL present → do not attach huge HTML
    assert with_url.attachment_paths(excel=True, html=True) == [excel]


def test_resolve_report_url(monkeypatch):
    from framework.notify.service import resolve_report_url

    monkeypatch.setenv("REPORT_BASE_URL", "https://uitest.example.com/reports/")
    monkeypatch.setattr(
        "framework.notify.service.load_notify_config",
        lambda: {"report_url": {"base_url_env": "REPORT_BASE_URL"}},
    )
    url = resolve_report_url(
        "MG0557",
        html_path=Path("runs/MG0557/allure-report.html"),
        cfg={"report_url": {"base_url_env": "REPORT_BASE_URL"}},
    )
    assert url == "https://uitest.example.com/reports/MG0557/allure-report.html"


def test_build_report_payload_from_runs(tmp_path: Path, monkeypatch):
    req = "NOTIFY-DEMO"
    base = tmp_path / "runs" / req
    base.mkdir(parents=True)
    (base / "logs").mkdir()
    excel = base / f"{req}_结果回填.xlsx"
    excel.write_bytes(b"excel")
    (base / "allure-report.html").write_text("<html>ok</html>", encoding="utf-8")
    (base / "excel_backfill_summary.json").write_text(
        json.dumps(
            {
                "ok": True,
                "excel": str(excel),
                "stats": {"通过": 1, "失败": 2, "Block": 3},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (base / "logs" / "TC-FAIL.jsonl").write_text(
        '{"event": "case_fail"}\n', encoding="utf-8"
    )
    monkeypatch.setattr("framework.notify.service.req_dir", lambda rid: base)
    payload = build_report_payload(req, exit_code=1)
    assert payload.passed == 1
    assert payload.failed == 2
    assert payload.blocked == 3
    assert payload.excel_path == excel
    assert payload.html_path and payload.html_path.name == "allure-report.html"
    assert "TC-FAIL" in payload.failed_cases


def test_email_channel_stub():
    ch = create_channel("email", {})
    result = ch.send(ReportPayload(req_id="X", title="t"))
    assert result.ok is False
    assert "not implemented" in result.message


def test_feishu_file_type():
    assert _feishu_file_type(Path("a.xlsx")) == "xls"
    assert _feishu_file_type(Path("a.html")) == "stream"


def test_feishu_send_mocked(tmp_path: Path, monkeypatch):
    excel = tmp_path / "report.xlsx"
    excel.write_bytes(b"123")
    payload = ReportPayload(
        req_id="MG0557",
        title="demo",
        passed=1,
        failed=0,
        excel_path=excel,
    )
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "sec_test")
    monkeypatch.setenv("FEISHU_CHAT_ID", "oc_test")

    channel = FeishuChannel(
        {
            "app_id_env": "FEISHU_APP_ID",
            "app_secret_env": "FEISHU_APP_SECRET",
            "chat_id_env": "FEISHU_CHAT_ID",
            "upload_html": False,
        }
    )

    def fake_http(method, url, **kwargs):
        if "tenant_access_token" in url:
            return {"tenant_access_token": "tok"}
        if "messages" in url:
            body = kwargs.get("body") or {}
            assert body.get("receive_id") == "oc_test"
            return {"code": 0, "data": {"message_id": "m1"}}
        raise AssertionError(url)

    def fake_upload(url, **kwargs):
        assert kwargs["file_path"] == excel
        return {"code": 0, "data": {"file_key": "fk1"}}

    with (
        patch("framework.notify.channels.feishu._http_json", side_effect=fake_http),
        patch("framework.notify.channels.feishu._multipart_upload", side_effect=fake_upload),
    ):
        result = channel.send(payload)
    assert result.ok is True
    assert result.details["uploaded"][0]["file_key"] == "fk1"


def test_notify_report_disabled(monkeypatch):
    monkeypatch.setattr(
        "framework.notify.service.load_notify_config",
        lambda: {"enabled": False, "channels": {}},
    )
    results = notify_report("MG0557")
    assert len(results) == 1
    assert results[0].ok is False
    assert "disabled" in results[0].message
