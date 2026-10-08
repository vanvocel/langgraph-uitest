import json
from pathlib import Path

from framework.runner.allure_report import _is_single_file_html, sanitize_allure_results


def test_sanitize_strips_title_path(tmp_path: Path):
    payload = {
        "name": "case",
        "status": "passed",
        "titlePath": ["tests", "t.py"],
        "steps": [{"name": "s", "titlePath": ["x"]}],
    }
    path = tmp_path / "a-result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert sanitize_allure_results(tmp_path) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "titlePath" not in data
    assert "titlePath" not in data["steps"][0]
    assert data["name"] == "case"


def test_promote_step_screenshots(tmp_path: Path):
    payload = {
        "name": "case",
        "status": "passed",
        "steps": [
            {
                "name": "[8] assert_options",
                "attachments": [
                    {"name": "断言通过 [8] assert_options", "source": "a.png", "type": "image/png"}
                ],
            }
        ],
    }
    path = tmp_path / "a-result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from framework.runner.allure_report import promote_step_screenshots

    assert promote_step_screenshots(tmp_path) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["attachments"][0]["source"] == "a.png"


def test_is_single_file_html(tmp_path: Path):
    empty = tmp_path / "empty.html"
    empty.write_text("<html></html>", encoding="utf-8")
    assert _is_single_file_html(empty) is False
    big = tmp_path / "report.html"
    big.write_text("<!doctype html><title>Allure Report</title>" + ("x" * 25_000), encoding="utf-8")
    assert _is_single_file_html(big) is True
