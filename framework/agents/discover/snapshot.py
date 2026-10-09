"""Compact page snapshot for LLM locator suggestions."""

from __future__ import annotations

from playwright.sync_api import Page

# Prefer dialog / score-table / main interactive; demote sidebar noise.
_SNAPSHOT_JS = """() => {
  const out = [];
  const seen = new Set();
  const inAside = (el) => !!(el.closest('aside') || el.closest('.el-menu') || el.closest('.md-sidebar'));
  const inDialog = (el) => !!(el.closest('.el-dialog') || el.closest('[role="dialog"]'));
  const inScore = (el) => !!(el.closest('table.score-table') || el.closest('.score-table'));
  const push = (el, kind, bonus) => {
    if (!(el instanceof HTMLElement)) return;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
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
    const aria = el.getAttribute('aria-label') || '';
    const ph = el.getAttribute('placeholder') || '';
    const key = [tag, role, text, cls, testid, id, aria, ph].join('|');
    if (seen.has(key)) return;
    seen.add(key);
    let pri = bonus || 0;
    if (inDialog(el)) pri += 100;
    if (inScore(el)) pri += 80;
    if (inAside(el)) pri -= 50;
    out.push({ kind, tag, role, text, cls, testid, id, aria, placeholder: ph, pri });
  };

  // Visible dialogs first (whole dialog + children).
  for (const dlg of document.querySelectorAll('.el-dialog, [role="dialog"]')) {
    const style = window.getComputedStyle(dlg);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    push(dlg, 'dialog', 120);
    for (const el of dlg.querySelectorAll(
      'button, a, input, textarea, select, [role], .el-select, .el-select__wrapper, .el-input, .el-button, .el-cascader, .el-tree, .el-checkbox, label, th'
    )) {
      push(el, 'dialog-child', 110);
    }
  }

  for (const el of document.querySelectorAll('table.score-table, .score-table')) {
    push(el, 'score-table', 90);
    for (const child of el.querySelectorAll('button, input, textarea, th, td, .el-input__inner')) {
      push(child, 'score-child', 85);
    }
  }

  for (const el of document.querySelectorAll(
    'button, a, input, textarea, select, [role], .el-select, .el-select__wrapper, .el-input, .el-button, .el-tabs__item, .el-check-tag, .el-table'
  )) {
    push(el, 'interactive', 10);
  }
  for (const el of document.querySelectorAll('label, th, .el-form-item__label')) {
    push(el, 'label', 5);
  }

  out.sort((a, b) => (b.pri || 0) - (a.pri || 0));
  return out.slice(0, 200).map(({pri, ...rest}) => rest);
}"""


def page_snapshot(page: Page) -> list[dict]:
    try:
        data = page.evaluate(_SNAPSHOT_JS)
    except Exception:  # noqa: BLE001
        return []
    return list(data or [])


def snapshot_text(page: Page, *, limit: int = 14000) -> str:
    rows = page_snapshot(page)
    lines = [f"url={page.url}"]
    # Flag open dialogs for the model.
    try:
        dlg_n = page.locator(".el-dialog:visible, [role='dialog']").count()
        lines.append(f"visible_dialogs={dlg_n}")
    except Exception:  # noqa: BLE001
        pass
    for i, row in enumerate(rows):
        lines.append(
            f"{i}|{row.get('kind')}|tag={row.get('tag')}|role={row.get('role')}"
            f"|text={row.get('text')}|aria={row.get('aria')}|placeholder={row.get('placeholder')}"
            f"|cls={row.get('cls')}|testid={row.get('testid')}|id={row.get('id')}"
        )
    text = "\n".join(lines)
    return text[:limit]
