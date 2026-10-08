"""Capture short-lived toasts via a DOM observer that survives the node being removed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from playwright.sync_api import BrowserContext, Page

from framework.paths import project_root

_QUEUES: dict[int, list[dict[str, Any]]] = {}

_INSTALL_JS = """
(() => {
  if (window.__toastInstalled) return;
  window.__toastInstalled = true;
  const SELECTOR = ".el-message, .el-notification";
  const seen = new Set();
  const levelOf = (el) => {
    const c = String(el.className || "");
    const levels = ["error", "success", "warning", "info"];
    for (const lv of levels) {
      if (c.includes("--" + lv) || c.includes("is-" + lv)) return lv;
    }
    return "info";
  };
  const push = (el) => {
    if (!el || el.nodeType !== 1 || !el.matches) return;
    if (!el.matches(SELECTOR)) return;
    const text = (el.innerText || "").replace(/\\s+/g, " ").trim();
    const level = levelOf(el);
    const key = level + "|" + text;
    if (seen.has(key)) return;
    seen.add(key);
    const payload = { level, text, ts: Date.now() };
    if (typeof window.__reportToast === "function") {
      window.__reportToast(payload);
    }
  };
  const scan = (node) => {
    if (!node || node.nodeType !== 1) return;
    if (node.matches && node.matches(SELECTOR)) push(node);
    if (node.querySelectorAll) node.querySelectorAll(SELECTOR).forEach(push);
  };
  const obs = new MutationObserver((mutations) => {
    for (const m of mutations) m.addedNodes.forEach(scan);
  });
  const start = () => {
    if (!document.body) return;
    obs.observe(document.body, { childList: true, subtree: true });
  };
  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
"""


def load_toast_rules() -> dict[str, Any]:
    path = Path(project_root()) / "framework" / "toast" / "rules.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def install_toast_bridge(context: BrowserContext) -> None:
    """Bind a toast reporter on the browser context (once)."""
    if getattr(context, "_toast_ready", False):
        return
    queue: list[dict[str, Any]] = []

    def _handle(_source: Any, payload: dict[str, Any]) -> None:
        if isinstance(payload, dict):
            queue.append(payload)

    context.expose_binding("__reportToast", _handle)
    context.add_init_script(_INSTALL_JS)
    _QUEUES[id(context)] = queue
    context._toast_ready = True  # type: ignore[attr-defined]


def toast_queue(page: Page) -> list[dict[str, Any]]:
    context = page.context
    install_toast_bridge(context)
    return _QUEUES.setdefault(id(context), [])


def arm_toast_listener(page: Page) -> int:
    """Start observing the current document. Returns queue cursor."""
    queue = toast_queue(page)
    page.evaluate(_INSTALL_JS)
    return len(queue)


def toasts_since(page: Page, cursor: int) -> list[dict[str, Any]]:
    return list(toast_queue(page)[cursor:])
