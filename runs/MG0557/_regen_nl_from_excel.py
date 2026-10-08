"""Regenerate MG0557 NL from Excel dump only (YAML must come from LLM compile)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DUMP = ROOT.parent / "MG0557_excel_dump.json"

AI_OUTBOUND = {"TC-QXGZ-016", "TC-QXGZ-017", "TC-QXGZ-019", "TC-QXGZ-025"}
NEEDS_FIXTURE = {
    "TC-QXGZ-004",
    "TC-QXGZ-007",
    "TC-QXGZ-008",
    "TC-QXGZ-009",
    "TC-QXGZ-011",
    "TC-QXGZ-012",
    "TC-QXGZ-018",
    "TC-QXGZ-020",
    "TC-QXGZ-023",
    "TC-QXGZ-024",
    "TC-QXGZ-026",
    "TC-QXGZ-034",
    "TC-QXGZ-035",
    "TC-QXGZ-036",
}


def main() -> None:
    raw = json.loads(DUMP.read_text(encoding="utf-8"))
    rows = raw["rows"][2:]
    nl_dir = ROOT / "nl"
    nl_dir.mkdir(exist_ok=True)
    n = 0
    for row in rows:
        if len(row) < 7 or not row[2]:
            continue
        case_id, title, pre, steps, expect = row[2], row[3], row[4], row[5], row[6]
        lines = [
            f"用例 {case_id}：{title}",
            "已登录（账号 default_tester）。",
        ]
        if case_id in AI_OUTBOUND:
            lines.append(
                "【人工/AI外呼】依赖第三方 AI 外呼回传，自动集不执行；编译时 tags 含 manual,ai_outbound，meta.manual_only=true。"
            )
        elif case_id in NEEDS_FIXTURE:
            lines.append(
                "【需造数】需造数/跨模块/故障注入/只读账号等前置，自动集暂不执行；编译时 tags 含 needs_fixture，meta.needs_fixture=true。"
            )
        lines.extend(
            [
                f"页面入口：https://lead.z-niu.com/rule/clean/ ，进入页签【清洗评分规则】。",
                f"前置：{pre}",
                "步骤（请逐步编译为 YAML，勿省略边界值/校验点）：",
                steps,
                f"预期：{expect}",
            ]
        )
        (nl_dir / f"{case_id}.nl.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        n += 1
        print("nl", case_id)
    print("wrote", n, "nl files")


if __name__ == "__main__":
    main()
