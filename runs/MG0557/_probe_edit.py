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

    page.get_by_role("tab", name="清洗评分规则").click(timeout=8000)
    page.wait_for_timeout(2000)

    # scroll score sections into view
    page.evaluate(
        """() => {
          const el = [...document.querySelectorAll('*')].find(e => (e.innerText||'').trim()==='获客渠道评分');
          if (el) el.scrollIntoView({block:'center'});
        }"""
    )
    page.wait_for_timeout(500)

    before = page.evaluate(
        """() => {
          const t = document.body.innerText || '';
          return {
            hasAdd: t.includes('添加渠道'),
            hasModify: t.includes('修改'),
            hasChannel: t.includes('获客渠道评分'),
            hasL1: t.includes('一级渠道'),
            hasL2: t.includes('二级渠道'),
            hasScore: t.includes('得分'),
            hasRemove: t.includes('移除'),
            hasAI: t.includes('AI清洗评分'),
            hasTimes: t.includes('已清洗次数评分'),
            hasUnclean: t.includes('未清洗'),
            hasLayer: t.includes('层差') || t.includes('维度分层'),
            hasLog: t.includes('修改日志'),
            hasSave: !!Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim()==='保存'),
          };
        }"""
    )

    # click 修改 (prefer button near score area)
    btn = page.get_by_role("button", name="修改")
    if btn.count() == 0:
        btn = page.locator("button", has_text="修改")
    btn.first.click(timeout=5000)
    page.wait_for_timeout(2000)

    after = page.evaluate(
        """() => {
          const t = document.body.innerText || '';
          const buttons = Array.from(document.querySelectorAll('button'))
            .map(b => (b.innerText||'').replace(/\\s+/g,' ').trim())
            .filter(Boolean);
          return {
            hasAdd: t.includes('添加渠道'),
            hasCancel: t.includes('取消'),
            hasSave: t.includes('保存'),
            hasRemove: t.includes('移除'),
            buttons: [...new Set(buttons)].slice(0, 40),
            dialogs: Array.from(document.querySelectorAll('.el-dialog,.el-drawer,.el-popup'))
              .filter(e => e.offsetParent)
              .map(e => (e.innerText||'').slice(0, 200)),
          };
        }"""
    )

    if after.get("hasAdd"):
        page.get_by_role("button", name="添加渠道").first.click(timeout=5000)
        page.wait_for_timeout(1500)
        picker = page.evaluate(
            """() => {
              const t = document.body.innerText || '';
              const visible = Array.from(document.querySelectorAll('.el-dialog,.el-drawer,.el-select-dropdown,.el-popover,.el-tree'))
                .filter(e => e.offsetParent)
                .map(e => ({
                  cls: e.className.slice(0,80),
                  text: (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0, 400)
                }));
              return {
                hasSlash: t.includes('/'),
                hasSearch: !!document.querySelector('input[placeholder*=搜索],input[placeholder*=请输入],.el-input__inner'),
                panels: visible,
              };
            }"""
        )
    else:
        picker = {"skipped": True}

    out = {"before": before, "after": after, "picker": picker}
    (OUT / "edit_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    page.screenshot(path=str(OUT / "edit_probe.png"), full_page=True)
    print(json.dumps(out, ensure_ascii=False, indent=2)[:3000])
    c.close()
    b.close()
    p.stop()


if __name__ == "__main__":
    main()
