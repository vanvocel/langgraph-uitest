"""Heuristic locator candidates. LLM is optional later; execution still has no LLM."""

from __future__ import annotations

from collections.abc import Iterator

from playwright.sync_api import Page

from framework.pom.loader import LocatorDef, resolve_locator

_MIN_CONFIDENCE = 0.65

_ROLE_BUTTONISH = ("button", "tab", "link", "menuitem")


def _form_control_xpath(name: str) -> str:
    return (
        f"//*[normalize-space()={_xq(name)} and not(ancestor::*[contains(@class,'el-table')]) "
        "and not(ancestor::aside) and not(ancestor::*[contains(@class,'el-menu')])]"
        "/following::*[contains(@class,'el-select__wrapper') or contains(@class,'el-select') "
        "or contains(@class,'el-input') or self::input or self::textarea][1]"
    )


def _xq(text: str) -> str:
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def iter_candidates(name: str) -> Iterator[LocatorDef]:
    if name in {"页面"}:
        yield LocatorDef(by="css", value="body")
        return
    if name in {"列表表格", "表格"}:
        yield LocatorDef(by="css", value="table.score-table")
        yield LocatorDef(by="css", value=".score-table")
        yield LocatorDef(by="css", value=".el-table")
        yield LocatorDef(by="css", value="table")
        return
    if name in {"列表行"}:
        yield LocatorDef(by="css", value=".el-table__body tbody tr:not(.el-table__empty-row)")
        return
    if name in {"弹窗"}:
        yield LocatorDef(by="css", value=".el-dialog:visible")
        yield LocatorDef(by="css", value=".el-dialog:not([style*='display: none'])")
        yield LocatorDef(by="css", value="[role='dialog']")
        return
    if name in {"弹窗关闭"}:
        yield LocatorDef(by="css", value=".el-dialog:visible .el-dialog__headerbtn")
        yield LocatorDef(by="css", value=".el-dialog .el-dialog__headerbtn")
        return
    if name in {"批量领取"}:
        yield LocatorDef(by="text", value="批量领取", exact=True)
        yield LocatorDef(by="role", value="button", name="批量领取", exact=True)
        return
    if name in {"下载中心"}:
        yield LocatorDef(by="text", value="下载中心", exact=True)
        yield LocatorDef(by="role", value="button", name="下载中心", exact=True)
        return
    # Icon-only delete in score / edit tables (visible text often absent).
    if name in {"移除", "删除图标", "删除行"}:
        yield LocatorDef(by="css", value="table.score-table button[aria-label='移除']")
        yield LocatorDef(by="css", value=".score-operation-column button[aria-label='移除']")
        yield LocatorDef(by="css", value="button[aria-label='移除']")
        yield LocatorDef(by="css", value="[aria-label='移除']")
        yield LocatorDef(by="role", value="button", name="移除", exact=True)
        yield LocatorDef(by="xpath", value=f"//*[@aria-label={_xq(name)}]")
        return
    if name in {"获客渠道评分"}:
        # Prefer the score table itself — section title text is often off-screen / nested.
        yield LocatorDef(by="css", value="table.score-table")
        yield LocatorDef(by="css", value=".score-table")
        yield LocatorDef(by="text", value="获客渠道评分", exact=True)
        yield LocatorDef(by="xpath", value=f"//*[contains(normalize-space(),{_xq(name)})]")
        return
    # Live title may be「AI外呼评分」; semantic YAML name is often「AI清洗评分」.
    if name in {"AI清洗评分", "AI外呼评分"}:
        yield LocatorDef(
            by="xpath",
            value=(
                "//table[.//th[normalize-space()='清洗方式'] "
                "and .//th[contains(normalize-space(),'得分')]]"
            ),
        )
        yield LocatorDef(
            by="xpath",
            value="//*[normalize-space()='AI外呼评分']/following::table[1]",
        )
        yield LocatorDef(
            by="xpath",
            value="//*[normalize-space()='AI清洗评分']/following::table[1]",
        )
        yield LocatorDef(by="text", value="AI外呼评分", exact=True)
        yield LocatorDef(by="text", value="AI清洗评分", exact=True)
        return
    if name in {"已清洗次数评分"}:
        yield LocatorDef(
            by="xpath",
            value=(
                "//table[.//th[contains(normalize-space(),'清洗次数') "
                "or contains(normalize-space(),'累计清洗')] "
                "and .//th[contains(normalize-space(),'得分')]]"
            ),
        )
        yield LocatorDef(
            by="xpath",
            value="//*[normalize-space()='已清洗次数评分']/following::table[1]",
        )
        yield LocatorDef(by="text", value="已清洗次数评分", exact=True)
        return
    if name in {"取消"}:
        yield LocatorDef(by="role", value="button", name="取消", exact=True)
        yield LocatorDef(by="text", value="取消", exact=True)
        yield LocatorDef(by="css", value="button:has-text('取消')")
        return
    if name in {"得分输入框", "渠道得分"}:
        yield LocatorDef(by="css", value="table.score-table input.el-input__inner")
        yield LocatorDef(by="css", value="table.score-table .el-input__inner")
        yield LocatorDef(by="css", value="table.score-table input")
        yield LocatorDef(by="css", value=".score-table input.el-input__inner")
        yield LocatorDef(by="css", value=".score-table input")
        return
    if name in {"获客渠道得分输入框"}:
        yield LocatorDef(
            by="xpath",
            value=(
                "//table[.//th[contains(normalize-space(),'一级渠道')]"
                "]//input[contains(@class,'el-input__inner') or true]"
            ),
        )
        yield LocatorDef(
            by="css",
            value="table.score-table:has(th:has-text('一级渠道')) input",
        )
        return
    if name in {"AI清洗得分输入框"}:
        yield LocatorDef(
            by="xpath",
            value="//table[.//th[normalize-space()='清洗方式']]//input",
        )
        yield LocatorDef(
            by="css",
            value="table.score-table:has(th:has-text('清洗方式')) input",
        )
        return
    if name in {"已清洗次数得分输入框"}:
        yield LocatorDef(
            by="xpath",
            value=(
                "//table[.//th[contains(normalize-space(),'清洗次数')"
                " or contains(normalize-space(),'累计清洗')]]//input"
            ),
        )
        yield LocatorDef(
            by="css",
            value="table.score-table:has(th:has-text('清洗次数')) input",
        )
        return
    if name in {"渠道选择器"}:
        yield LocatorDef(by="css", value=".el-dialog:visible .el-cascader")
        yield LocatorDef(by="css", value=".el-dialog:visible .el-tree")
        yield LocatorDef(by="css", value=".el-dialog:visible .el-select")
        yield LocatorDef(by="css", value=".el-dialog:visible .el-dialog__body")
        yield LocatorDef(by="css", value="[role='dialog'] .el-cascader")
        return
    if name in {"渠道搜索框"}:
        yield LocatorDef(by="css", value=".el-dialog:visible input[placeholder*='搜索']")
        yield LocatorDef(by="css", value=".el-dialog:visible .el-input__inner")
        yield LocatorDef(by="css", value=".el-dialog:visible input")
        yield LocatorDef(by="placeholder", value="搜索")
        return
    if name in {"确认添加"}:
        yield LocatorDef(by="role", value="button", name="确认添加", exact=True)
        yield LocatorDef(by="text", value="确认添加", exact=True)
        yield LocatorDef(by="css", value=".el-dialog:visible button:has-text('确认添加')")
        return
    if name in {"已添加渠道勾选框", "已添加渠道选项"}:
        yield LocatorDef(by="css", value=".el-dialog:visible .el-checkbox")
        yield LocatorDef(by="css", value=".el-dialog:visible .el-checkbox__label")
        yield LocatorDef(by="role", value="checkbox", name="已添加", exact=False)
        return
    if name in {"未添加渠道选项"}:
        yield LocatorDef(by="css", value=".el-dialog:visible .el-checkbox")
        yield LocatorDef(by="css", value=".el-dialog:visible .el-checkbox__label")
        yield LocatorDef(by="text", value="未添加", exact=False)
        return
    if name in {"配置表"}:
        yield LocatorDef(by="css", value="table.score-table")
        yield LocatorDef(by="css", value=".score-table")
        yield LocatorDef(by="css", value=".el-table")
        return
    if name in {"配置表渠道行"}:
        yield LocatorDef(by="css", value="table.score-table tbody tr")
        yield LocatorDef(by="css", value=".score-table tbody tr")
        yield LocatorDef(by="css", value=".el-table__body tbody tr:not(.el-table__empty-row)")
        return
    if name in {"层差校验弹窗", "层差不通过提示", "二次确认"}:
        yield LocatorDef(by="css", value=".el-dialog:visible")
        yield LocatorDef(by="css", value=".el-message-box:visible")
        yield LocatorDef(by="css", value="[role='dialog']")
        yield LocatorDef(by="text", value=name, exact=False)
        return
    if name in {"返回调整", "已知风险仍保存"}:
        yield LocatorDef(by="role", value="button", name=name, exact=True)
        yield LocatorDef(by="text", value=name, exact=True)
        yield LocatorDef(by="css", value=f".el-dialog:visible button:has-text('{name}')")
        return
    if name in {"保存成功", "保存成功提示"}:
        yield LocatorDef(by="css", value=".el-message:visible")
        yield LocatorDef(by="css", value=".el-notification:visible")
        yield LocatorDef(by="text", value="保存成功", exact=False)
        return
    if name in {"表单校验提示", "校验提示"}:
        yield LocatorDef(by="css", value=".el-form-item__error")
        yield LocatorDef(by="css", value=".el-form-item__error:visible")
        yield LocatorDef(by="css", value=".el-message--error:visible")
        yield LocatorDef(by="css", value=".el-message-box:visible")
        return
    if name in {"添加渠道"}:
        yield LocatorDef(by="role", value="button", name="添加渠道", exact=True)
        yield LocatorDef(by="text", value="添加渠道", exact=True)
        return
    if name in {"一级", "二级"}:
        yield LocatorDef(by="role", value="tab", name=name, exact=True)
        yield LocatorDef(by="css", value=".el-dialog:visible .el-tabs__item")
        yield LocatorDef(
            by="xpath",
            value=f"//th[normalize-space()={_xq(name)} or contains(normalize-space(),{_xq(name+'渠道')})]",
        )
        yield LocatorDef(by="text", value=name, exact=True)
        return
    # Short action names that are prefixes of others (修改 vs 修改日志) — exact only.
    if name in {"修改", "保存", "添加", "删除", "查询", "重置", "导出", "确认"}:
        yield LocatorDef(by="role", value="button", name=name, exact=True)
        yield LocatorDef(by="text", value=name, exact=True)
        return
    # Known page tabs — prefer role=tab over bare text (avoids sidebar / heading hits).
    if name in {
        "清洗评分规则",
        "人工待清洗",
        "AI外呼待清洗",
        "AI 外呼待清洗",
        "清洗记录",
        "已清洗客资",
    }:
        yield LocatorDef(by="role", value="tab", name=name, exact=True)
        yield LocatorDef(by="text", value=name, exact=True)
        return

    for role in _ROLE_BUTTONISH:
        yield LocatorDef(by="role", value=role, name=name, exact=True)
    yield LocatorDef(by="text", value=name, exact=True)
    yield LocatorDef(by="placeholder", value=name)
    yield LocatorDef(by="label", value=name, exact=True)
    yield LocatorDef(by="testid", value=name)
    yield LocatorDef(by="css", value=f"[aria-label={_css_attr(name)}]")
    yield LocatorDef(by="xpath", value=f"//*[@aria-label={_xq(name)}]")
    yield LocatorDef(by="xpath", value=_form_control_xpath(name))
    # Non-exact role last; validate_locator rejects prefix collisions.
    for role in _ROLE_BUTTONISH:
        yield LocatorDef(by="role", value=role, name=name, exact=False)


def _css_attr(text: str) -> str:
    if "'" not in text:
        return f"'{text}'"
    return f'"{text}"'


def _controlish(element_name: str) -> bool:
    n = element_name or ""
    return any(
        key in n
        for key in (
            "输入框",
            "搜索框",
            "选择器",
            "勾选",
            "开关",
            "按钮",
            "得分输入",
            "渠道得分",
        )
    )


def _semantic_ok(element_name: str, locator: LocatorDef) -> bool:
    """Reject role/text candidates whose label clearly belongs to another control."""
    if locator.by in {"css", "xpath", "id", "testid"}:
        return True
    needle = "".join((element_name or "").split())
    if not needle:
        return True
    hay = "".join(((locator.name or locator.value or "")).split())
    if not hay:
        return True
    # Allow substring either way (e.g. name=获客渠道评分维度开关 vs 获客渠道评分).
    if needle in hay or hay in needle:
        return True
    return False


def validate_locator(
    page: Page,
    locator: LocatorDef,
    *,
    element_name: str | None = None,
) -> float | None:
    if element_name and not _semantic_ok(element_name, locator):
        return None
    try:
        loc = resolve_locator(page, locator)
        count = loc.count()
    except Exception:  # noqa: BLE001
        return None
    if count < 1:
        return None
    # Prefer an enabled, visible match (skip disabled EP buttons / hidden clones).
    chosen = None
    for i in range(min(count, 8)):
        item = loc.nth(i)
        try:
            if not item.is_visible():
                continue
            try:
                if not item.is_enabled():
                    continue
            except Exception:  # noqa: BLE001
                pass
            # Reject sidebar menu labels when looking for main-content filters.
            try:
                in_aside = item.evaluate(
                    "el => !!(el.closest('aside') || el.closest('.el-menu') || el.closest('.md-sidebar'))"
                )
            except Exception:  # noqa: BLE001
                in_aside = False
            if in_aside and locator.by in {"text", "placeholder", "label"}:
                continue
            try:
                kind = item.evaluate(
                    """el => {
                      const tag = (el.tagName || '').toLowerCase();
                      const cls = String(el.className || '');
                      const role = (el.getAttribute('role') || '').toLowerCase();
                      const help = !!(
                        el.closest('.score-note') || el.closest('.el-alert')
                        || cls.includes('score-note') || cls.includes('el-alert')
                      );
                      const hasInput = !!(
                        el.matches('input,textarea,[contenteditable="true"]')
                        || el.querySelector('input,textarea,[contenteditable="true"]')
                      );
                      const hasCheckbox = !!(
                        el.matches('input[type=checkbox],.el-checkbox,[role=checkbox]')
                        || el.querySelector('input[type=checkbox],.el-checkbox,[role=checkbox]')
                      );
                      const isDialog = !!(
                        el.closest('.el-dialog,.el-message-box,[role=dialog]')
                        || role === 'dialog'
                        || cls.includes('el-dialog')
                      );
                      return {tag, help, hasInput, hasCheckbox, isDialog};
                    }"""
                )
            except Exception:  # noqa: BLE001
                kind = {}
            tag = str((kind or {}).get("tag") or "")
            if element_name and _controlish(element_name):
                if tag in {"th", "td", "thead", "caption"}:
                    continue
                if kind.get("help"):
                    continue
                if ("输入" in element_name or "搜索框" in element_name or "渠道得分" in element_name) and not kind.get(
                    "hasInput"
                ):
                    continue
                if "勾选" in element_name and not kind.get("hasCheckbox"):
                    continue
            if element_name and ("弹窗" in element_name or element_name in {"二次确认"}):
                if not kind.get("isDialog"):
                    continue
            # Reject non-exact role/text hits whose accessible name is a longer
            # sibling (e.g. name=修改 matching 修改日志).
            if element_name and locator.exact is False and locator.by in {"role", "text"}:
                try:
                    acc = (item.inner_text() or "").strip() or (
                        item.get_attribute("aria-label") or ""
                    ).strip()
                except Exception:  # noqa: BLE001
                    acc = ""
                compact_name = "".join(element_name.split())
                compact_acc = "".join(acc.split())
                if compact_acc and compact_acc != compact_name and compact_name in compact_acc:
                    continue
            chosen = item
            break
        except Exception:  # noqa: BLE001
            continue
    if chosen is None:
        return None
    if count == 1:
        return 0.95
    return 0.8


def _same_locator(a: LocatorDef, b: LocatorDef) -> bool:
    return (
        a.by == b.by
        and a.value == b.value
        and a.name == b.name
        and bool(a.exact) == bool(b.exact)
    )


def bind_element(
    page: Page,
    name: str,
    *,
    extra: list[LocatorDef] | None = None,
    exclude: LocatorDef | None = None,
) -> tuple[LocatorDef, float] | None:
    best: tuple[LocatorDef, float] | None = None
    # LLM / extra candidates first (often more specific), then heuristics.
    ordered = list(extra or []) + list(iter_candidates(name))
    for cand in ordered:
        if exclude is not None and _same_locator(cand, exclude):
            continue
        score = validate_locator(page, cand, element_name=name)
        if score is None:
            continue
        if score >= 0.9:
            return cand, score
        if best is None or score > best[1]:
            best = (cand, score)
    if best and best[1] >= _MIN_CONFIDENCE:
        return best
    return None
