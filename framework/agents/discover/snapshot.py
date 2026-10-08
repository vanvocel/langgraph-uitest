"""Compact page snapshot for LLM locator suggestions."""

from __future__ import annotations

from playwright.sync_api import Page

_SNAPSHOT_JS = """() => {
  const out = [];
  const seen = new Set();
  const push = (el, kind) => {
    if (!(el instanceof HTMLElement) || !el.offsetParent && el !== document.body) return;
    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    const role = el.getAttribute('role') || '';
    const tag = el.tagName.toLowerCase();
    const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '')
      .replace(/\\s+/g, ' ').trim().slice(0, 80);
    const cls = (el.className && typeof el.className === 'string')
      ? el.className.split(/\\s+/).filter(Boolean).slice(0, 6).join(' ')
      : '';
    const testid = el.getAttribute('data-testid') || '';
    const id = el.id || '';
    const key = [tag, role, text, cls, testid, id].join('|');
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ kind, tag, role, text, cls, testid, id });
  };
  for (const el of document.querySelectorAll(
    'button, a, input, textarea, select, [role], .el-select, .el-select__wrapper, .el-input, .el-button, .el-tabs__item, .el-check-tag, .el-dialog, .el-table, .md-sidebar__menu-item-label, .md-sidebar__group-title'
  )) {
    push(el, 'interactive');
  }
  for (const el of document.querySelectorAll('label, th, .el-form-item__label')) {
    push(el, 'label');
  }
  return out.slice(0, 180);
}"""


def page_snapshot(page: Page) -> list[dict]:
    try:
        data = page.evaluate(_SNAPSHOT_JS)
    except Exception:  # noqa: BLE001
        return []
    return list(data or [])


def snapshot_text(page: Page, *, limit: int = 12000) -> str:
    rows = page_snapshot(page)
    lines = [f"url={page.url}"]
    for i, row in enumerate(rows):
        lines.append(
            f"{i}|{row.get('kind')}|tag={row.get('tag')}|role={row.get('role')}|text={row.get('text')}"
            f"|cls={row.get('cls')}|testid={row.get('testid')}|id={row.get('id')}"
        )
    text = "\n".join(lines)
    return text[:limit]
