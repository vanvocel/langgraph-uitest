from pathlib import Path

from playwright.sync_api import sync_playwright

from framework.agents.discover.candidates import bind_element
from framework.agents.discover.collect import collect_elements, collect_urls
from framework.agents.discover.llm_candidates import parse_llm_candidates
from framework.agents.discover.service import discover_requirement
from framework.schema.case import UiCase


def test_collect_urls_and_elements():
    case = UiCase.model_validate(
        {
            "case_id": "A",
            "title": "t",
            "steps": [
                {"action": "open", "url": "https://example.com/a"},
                {"action": "click", "element": "查询"},
                {"action": "click", "element": "查询"},
            ],
        }
    )
    assert collect_urls([case]) == ["https://example.com/a"]
    assert collect_elements([case]) == ["查询"]


def test_bind_element_on_local_html(tmp_path: Path):
    html = tmp_path / "p.html"
    html.write_text("<html><body><button>查询</button></body></html>", encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(html.as_uri())
        hit = bind_element(page, "查询")
        browser.close()
    assert hit is not None
    loc, score = hit
    assert loc.by == "role"
    assert loc.value == "button"
    assert loc.name == "查询"
    assert score >= 0.9


def test_discover_requirement_writes_pom():
    report = discover_requirement("DISCOVER-001", force=True, use_llm=False)
    assert report["blocked"] is False
    assert "查询" in report["bound"]
    pom = Path(report["pom"])
    text = pom.read_text(encoding="utf-8")
    assert "查询" in text
    assert "button" in text


def test_parse_llm_candidates():
    payload = {
        "candidates": [
            {
                "element": "查询",
                "locators": [
                    {"by": "role", "value": "button", "name": "查询", "exact": True},
                    {"by": "bogus", "value": "x"},
                ],
            }
        ]
    }
    parsed = parse_llm_candidates(payload)
    assert "查询" in parsed
    assert parsed["查询"][0].by == "role"
    assert parsed["查询"][0].name == "查询"
