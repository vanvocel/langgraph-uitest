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
    page.wait_for_timeout(1200)
    page.get_by_text("清洗评分规则", exact=True).first.click(timeout=5000)
    page.wait_for_timeout(1500)
    page.evaluate(
        """() => {
          const m = document.querySelector('main, .el-main, .md-main');
          if (m) m.scrollTop = 900;
          else window.scrollBy(0, 900);
        }"""
    )
    page.wait_for_timeout(400)
    edit = False
    try:
        page.get_by_role("button", name="修改").first.click(timeout=5000)
        page.wait_for_timeout(1500)
        edit = True
    except Exception as exc:  # noqa: BLE001
        print("modify fail", exc)

    info = page.evaluate(
        """() => {
          const texts = document.body.innerText || '';
          const has = (s) => texts.includes(s);
          const buttons = Array.from(document.querySelectorAll('button, .el-button'))
            .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim())
            .filter(Boolean);
          return {
            url: location.href,
            has: {
              获客渠道评分: has('获客渠道评分'),
              AI清洗评分: has('AI清洗评分'),
              已清洗次数评分: has('已清洗次数评分'),
              添加渠道: has('添加渠道'),
              未清洗: has('未清洗'),
              AI外呼: has('AI 外呼') || has('AI外呼'),
              留资方式评分: has('留资方式评分'),
              来源方式评分: has('来源方式评分'),
              层差: has('层差') || has('维度分层'),
              保存: has('保存'),
              取消: has('取消'),
            },
            buttons: [...new Set(buttons)].slice(0, 60),
            snippet: texts.slice(texts.indexOf('智能清洗评分'), texts.indexOf('智能清洗评分') + 1800),
          };
        }"""
    )
    info["edit"] = edit
    (OUT / "score_edit.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    page.screenshot(path=str(OUT / "score_edit.png"), full_page=True)
    for name in ("取消", "返回"):
        try:
            btn = page.get_by_role("button", name=name)
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=2000)
                break
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps({"edit": edit, "has": info["has"]}, ensure_ascii=False))
    c.close()
    b.close()
    p.stop()


if __name__ == "__main__":
    main()
