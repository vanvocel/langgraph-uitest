"""DeepSeek (or other OpenAI-compat) locator candidates. Validated before write."""

from __future__ import annotations

import json
import re
from typing import Any

from framework.llm.profiles import LlmProfile
from framework.pom.loader import LocatorDef

_ALLOWED_BY = {"css", "xpath", "role", "text", "testid", "id", "placeholder", "label"}

SYSTEM_PROMPT = """你是 UI 自动化定位专家。根据页面快照，为每个语义元素名给出 Playwright 定位候选。

硬性规则：
- 只输出 JSON 对象，不要 markdown
- 格式：{"candidates":[{"element":"语义名","locators":[{"by":"role|text|css|xpath|testid|id|placeholder|label","value":"...","name":"可选role名","exact":true}]}]}
- 每个 element 最多 4 个 locators，按稳妥程度排序
- Element Plus：Tab 用 by=role value=tab + name；按钮用 role=button
- 筛选下拉（清洗次数/来源/来源平台/任务状态等）必须用 xpath：label 文案后的 .el-select__wrapper，并排除 aside/el-menu/el-table
- 禁止用纯 text/placeholder 绑筛选框（会点到侧栏同名菜单）
- 禁止编造不存在的 data-testid；快照里没有就别用 testid
- value/name 必须贴近快照里的真实文案（含空格/标点）
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM output is not a JSON object")
    return data


def _to_locator(raw: dict[str, Any]) -> LocatorDef | None:
    by = str(raw.get("by") or "").strip().lower()
    value = str(raw.get("value") or "").strip()
    if by not in _ALLOWED_BY or not value:
        return None
    name = raw.get("name")
    exact = raw.get("exact")
    kwargs: dict[str, Any] = {"by": by, "value": value}
    if name is not None and str(name).strip():
        kwargs["name"] = str(name).strip()
    if exact is not None:
        kwargs["exact"] = bool(exact)
    try:
        return LocatorDef.model_validate(kwargs)
    except Exception:  # noqa: BLE001
        return None


def parse_llm_candidates(payload: dict[str, Any]) -> dict[str, list[LocatorDef]]:
    out: dict[str, list[LocatorDef]] = {}
    items = payload.get("candidates") or []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        element = str(item.get("element") or "").strip()
        if not element:
            continue
        locs: list[LocatorDef] = []
        for raw in item.get("locators") or []:
            if not isinstance(raw, dict):
                continue
            loc = _to_locator(raw)
            if loc is not None:
                locs.append(loc)
        if locs:
            out[element] = locs[:4]
    return out


def ask_locator_candidates(
    *,
    element_names: list[str],
    snapshot: str,
    profile: LlmProfile,
) -> dict[str, list[LocatorDef]]:
    if not element_names:
        return {}
    if not profile.has_key:
        raise ValueError(f"LLM profile {profile.name} has empty {profile.api_key_env}")

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=profile.model,
        api_key=profile.api_key,
        base_url=profile.base_url,
        temperature=profile.temperature,
    )
    human = (
        "需要绑定的语义元素名（必须全部给出候选）：\n"
        + "\n".join(f"- {n}" for n in element_names)
        + "\n\n页面快照：\n"
        + snapshot
        + "\n\n请只输出 JSON。"
    )
    result = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human)])
    content = result.content if hasattr(result, "content") else str(result)
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    data = _extract_json(str(content))
    return parse_llm_candidates(data)
