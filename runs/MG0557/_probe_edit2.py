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

    page.get_by_role("tab", name="清洗评分规则", exact=True).click(timeout=8000)
    page.wait_for_timeout(2000)

    mods = page.evaluate(
        """() => Array.from(document.querySelectorAll('button,a,[role=button]'))
          .map(e => ({
            tag: e.tagName,
            text: (e.innerText||e.textContent||'').replace(/\\s+/g,' ').trim(),
            cls: (e.className||'').toString().slice(0,60)
          }))
          .filter(x => x.text.includes('修改'))"""
    )

    page.get_by_role("button", name="修改", exact=True).click(timeout=8000)
    page.wait_for_timeout(2500)

    after = page.evaluate(
        """() => {
          const t = document.body.innerText || '';
          const active = Array.from(document.querySelectorAll('.el-tabs__item.is-active,[role=tab][aria-selected=true]'))
            .map(e => (e.innerText||'').trim());
          return {
            active,
            hasAdd: t.includes('添加渠道'),
            hasCancel: t.includes('取消'),
            hasSave: t.includes('保存'),
            hasScoreTitle: t.includes('获客渠道评分'),
            hasRemove: t.includes('移除'),
            hasAI: t.includes('AI清洗评分'),
            hasTimes: t.includes('已清洗次数评分'),
          };
        }"""
    )

    picker = {}
    if after.get("hasAdd"):
        page.get_by_role("button", name="添加渠道", exact=True).first.click(timeout=5000)
        page.wait_for_timeout(1500)
        picker = page.evaluate(
            """() => {
              const dlg = document.querySelector('.el-overlay-dialog[aria-label], .el-dialog');
              const text = dlg ? (dlg.innerText||'').replace(/\\s+/g,' ').trim() : '';
              const inputs = Array.from(document.querySelectorAll('.el-dialog input, .el-overlay-dialog input'))
                .map(e => e.getAttribute('placeholder') || e.getAttribute('aria-label') || '');
              const labels = Array.from(document.querySelectorAll('.el-dialog label, .el-checkbox, .el-tree-node__label'))
                .map(e => (e.innerText||'').trim()).filter(Boolean).slice(0, 30);
              return {
                aria: dlg ? dlg.getAttribute('aria-label') : null,
                text: text.slice(0, 800),
                inputs,
                labels,
                hasSlash: text.includes('/'),
              };
            }"""
        )
        page.screenshot(path=str(OUT / "picker.png"), full_page=False)
        # close dialog via Escape / 取消 inside dialog
        dlg_cancel = page.locator(".el-dialog").get_by_role("button", name="取消", exact=True)
        if dlg_cancel.count():
            dlg_cancel.first.click(timeout=5000)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(800)

    out = {"mods": mods, "after": after, "picker": picker}
    (OUT / "edit_probe2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    page.screenshot(path=str(OUT / "edit_probe2.png"), full_page=True)
    print(json.dumps(out, ensure_ascii=False, indent=2)[:3000])

    # discard edit
    page.keyboard.press("Escape")
    c.close()
    b.close()
    p.stop()


if __name__ == "__main__":
    main()
