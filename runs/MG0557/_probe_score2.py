from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from framework.bootstrap.login import ensure_logged_in, storage_state_for
from framework.browser.session import start_playwright

OUT = Path(__file__).resolve().parent


def main() -> None:
    state = storage_state_for("default_tester")
    p, b, c, page = start_playwright(storage_state=state)
    ensure_logged_in(page, account_ref="default_tester")
    page.goto("https://lead.z-niu.com/rule/clean/", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    tabs = page.evaluate(
        """() => Array.from(document.querySelectorAll('[role=tab], .el-tabs__item'))
          .map(e => ({
            text: (e.innerText||'').replace(/\\s+/g,' ').trim(),
            role: e.getAttribute('role'),
            cls: e.className,
            active: e.className.includes('is-active') || e.getAttribute('aria-selected')==='true'
          }))"""
    )
    (OUT / "tabs.json").write_text(json.dumps(tabs, ensure_ascii=False, indent=2), encoding="utf-8")

    # Prefer role=tab
    tab = page.get_by_role("tab", name="清洗评分规则")
    if tab.count() == 0:
        tab = page.locator(".el-tabs__item", has_text="清洗评分规则")
    tab.first.click(timeout=5000)
    page.wait_for_timeout(2000)

    info = page.evaluate(
        """() => {
          const t = document.body.innerText || '';
          return {
            url: location.href,
            activeTabs: Array.from(document.querySelectorAll('.el-tabs__item.is-active,[role=tab][aria-selected=true]'))
              .map(e => (e.innerText||'').trim()),
            hasScoreTitle: t.includes('智能清洗评分规则配置'),
            hasChannel: t.includes('获客渠道评分'),
            hasAI: t.includes('AI清洗评分'),
            hasTimes: t.includes('已清洗次数评分'),
            hasLayer: t.includes('维度分层'),
            idx: t.indexOf('智能清洗评分规则配置'),
            snippet: (() => {
              const i = t.indexOf('智能清洗评分');
              return i >= 0 ? t.slice(i, i+1200) : t.slice(0, 800);
            })(),
          };
        }"""
    )
    (OUT / "score_tab.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    page.screenshot(path=str(OUT / "score_tab.png"), full_page=True)
    print(json.dumps({k: info[k] for k in info if k != "snippet"}, ensure_ascii=False))
    c.close()
    b.close()
    p.stop()


if __name__ == "__main__":
    main()
