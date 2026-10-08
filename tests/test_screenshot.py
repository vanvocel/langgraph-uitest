"""Full-page screenshot captures nested scroll containers, not only the viewport."""

from __future__ import annotations

import struct
from pathlib import Path

from playwright.sync_api import sync_playwright

from framework.runner.screenshot import take_png

_HTML = """
<!doctype html>
<html>
<head>
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; }
  .shell { height: 100%; overflow: hidden; }
  .main { height: 100%; overflow: auto; }
  .tall { height: 2400px; background: linear-gradient(#fff, #08f); }
</style>
</head>
<body>
  <div class="shell"><div class="main"><div class="tall" id="marker">full</div></div></div>
</body>
</html>
"""


def _png_size(data: bytes) -> tuple[int, int]:
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_take_png_covers_inner_scroller(tmp_path: Path) -> None:
    html = tmp_path / "page.html"
    html.write_text(_HTML, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 800, "height": 500})
        page.goto(html.as_uri())
        viewport = page.screenshot(full_page=False)
        naive_full = page.screenshot(full_page=True)
        whole = take_png(page)
        browser.close()
    assert whole
    _, vh = _png_size(viewport)
    _, nh = _png_size(naive_full)
    _, wh = _png_size(whole)
    assert vh == 500
    assert nh <= 520
    assert wh >= 2000
