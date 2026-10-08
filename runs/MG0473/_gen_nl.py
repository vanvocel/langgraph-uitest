"""One-shot: YAML steps → NL markdown for compile."""

from __future__ import annotations

from pathlib import Path

from framework.schema.loader import list_case_files, load_case

ROOT = Path(__file__).resolve().parents[2]


def step_nl(s) -> str:
    a = s.action.value
    el = s.element or ""
    mapping = {
        "open": f"打开 {s.url}",
        "wait_visible": f"等待「{el}」可见",
        "click": f"点击「{el}」",
        "click_if_visible": f"如果看得到「{el}」就点一下",
        "multi_select": f"在「{el}」中多选：{s.value}",
        "select": f"在「{el}」中选择：{s.value}",
        "clear_select": f"清空「{el}」的已选项（现网无清空按钮可用全选对消）",
        "assert_options": f"断言「{el}」下拉选项为：{s.expect}",
        "assert_text_contains": f"断言「{el}」文案包含：{s.expect}",
        "assert_text_not_contains": f"断言「{el}」文案不包含：{s.expect}",
        "assert_headers": f"断言「{el}」表头包含/排除（!为不得出现）：{s.expect}",
        "assert_column": f"断言列「{el}」满足 {s.expect}",
        "assert_count": f"断言「{el}」数量 {s.expect}",
        "assert_filter_order": f"断言筛选字段顺序为：{s.expect}",
        "capture_column": f"把列「{el}」当前页取值记到变量 {s.value}",
        "assert_set": f"断言列「{el}」当前页集合与变量 {s.expect} 一致",
        "assert_set_disjoint": f"断言变量 {s.value} 与 {s.expect} 无交集",
    }
    if a in mapping:
        return mapping[a]
    extra = " ".join(x for x in (s.value, s.expect) if x)
    return f"{a} {el} {extra}".strip()


def main() -> None:
    nl_dir = ROOT / "runs" / "MG0473" / "nl"
    nl_dir.mkdir(exist_ok=True)
    yaml_dir = ROOT / "runs" / "MG0473" / "yaml"
    for path in list_case_files(yaml_dir):
        case = load_case(path)
        lines = [f"用例 {case.case_id}：{case.title}", "已登录。"]
        note = (case.meta or {}).get("live_notes")
        if note:
            lines.append(f"现网说明：{note}")
        lines.append("步骤：")
        for i, step in enumerate(case.steps, 1):
            lines.append(f"{i}. {step_nl(step)}")
        out = nl_dir / f"{path.stem}.nl.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("wrote", out.name)


if __name__ == "__main__":
    main()
