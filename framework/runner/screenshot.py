"""Full-page screenshots, including Element Plus inner scroll containers."""

from __future__ import annotations

from playwright.sync_api import Page

_MAX_EXPAND_PX = 20000

_EXPAND_JS = """(maxPx) => {
  const restores = [];
  const nodes = [document.documentElement, document.body, ...document.querySelectorAll("*")];
  const seen = new Set();
  const depth = (el) => {
    let n = 0;
    while (el) { n += 1; el = el.parentElement; }
    return n;
  };
  const ranked = nodes
    .filter((el) => el instanceof HTMLElement && !seen.has(el) && (seen.add(el) || true))
    .sort((a, b) => depth(b) - depth(a));
  for (const el of ranked) {
    const cs = getComputedStyle(el);
    const oy = cs.overflowY;
    const ox = cs.overflowX;
    const clipsY = oy === "auto" || oy === "scroll" || oy === "hidden" || oy === "overlay";
    const clipsX = ox === "auto" || ox === "scroll" || ox === "hidden" || ox === "overlay";
    const taller = el.scrollHeight > el.clientHeight + 1;
    const wider = el.scrollWidth > el.clientWidth + 1;
    const isRoot = el === document.documentElement || el === document.body;
    if (!isRoot && !((clipsY && taller) || (clipsX && wider))) continue;
    restores.push({ el, cssText: el.style.cssText });
    const h = Math.min(Math.max(el.scrollHeight, el.clientHeight), maxPx);
    const w = Math.min(Math.max(el.scrollWidth, el.clientWidth), maxPx);
    el.style.setProperty("height", `${h}px`, "important");
    el.style.setProperty("max-height", "none", "important");
    el.style.setProperty("width", `${w}px`, "important");
    el.style.setProperty("max-width", "none", "important");
    el.style.setProperty("overflow", "visible", "important");
    el.style.setProperty("overflow-x", "visible", "important");
    el.style.setProperty("overflow-y", "visible", "important");
  }
  window.__uitestShotRestore = restores;
}"""

_RESTORE_JS = """() => {
  const restores = window.__uitestShotRestore || [];
  for (const item of restores) {
    if (item && item.el) item.el.style.cssText = item.cssText || "";
  }
  window.__uitestShotRestore = null;
}"""


def take_png(page: Page) -> bytes | None:
    """Capture the whole page (document + nested scrollers), not just the viewport."""
    expanded = False
    try:
        page.evaluate(_EXPAND_JS, _MAX_EXPAND_PX)
        expanded = True
        return page.screenshot(full_page=True, timeout=60_000, animations="disabled")
    except Exception:  # noqa: BLE001
        try:
            return page.screenshot(full_page=True, timeout=60_000, animations="disabled")
        except Exception:  # noqa: BLE001
            try:
                return page.screenshot(full_page=False)
            except Exception:  # noqa: BLE001
                return None
    finally:
        if expanded:
            try:
                page.evaluate(_RESTORE_JS)
            except Exception:  # noqa: BLE001
                pass
