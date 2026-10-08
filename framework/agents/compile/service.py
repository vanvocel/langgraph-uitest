"""Compile NL files under runs/<req>/nl into yaml/*.yaml (overwrite)."""

from __future__ import annotations

from pathlib import Path

import yaml

from framework.agents.compile.graph import compile_nl
from framework.paths import init_requirement, req_dir


def _nl_stem(path: Path) -> str:
    name = path.name
    for suf in (".nl.md", ".md", ".txt", ".nl"):
        if name.lower().endswith(suf):
            return name[: -len(suf)]
    return path.stem


def list_nl_files(nl_dir: Path) -> list[Path]:
    if not nl_dir.is_dir():
        return []
    files: list[Path] = []
    for p in sorted(nl_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in {".md", ".txt", ".nl"}:
            files.append(p)
    return files


def _apply_skip_tags(case: dict, nl_text: str) -> dict:
    """Skip tags follow NL banners only — do not trust LLM-invented Block tags."""
    tags = [str(t) for t in (case.get("tags") or [])]
    meta = dict(case.get("meta") or {})
    text = nl_text or ""

    tags = [
        t
        for t in tags
        if str(t).lower() not in {"manual", "ai_outbound", "needs_fixture"}
    ]
    meta.pop("manual_only", None)
    meta.pop("needs_fixture", None)

    if "【人工/AI外呼】" in text:
        tags.extend(["manual", "ai_outbound"])
        meta["manual_only"] = True
    elif "【需造数】" in text or "【needs_fixture】" in text:
        tags.append("needs_fixture")
        meta["needs_fixture"] = True

    case["tags"] = tags
    case["meta"] = meta
    return case


def compile_requirement(
    req_id: str,
    *,
    llm_profile: str | None = None,
    force_backend: str = "",
) -> list[dict]:
    """NL → yaml/<case_id>.yaml. Overwrites any existing file with the same name."""
    init_requirement(req_id)
    base = req_dir(req_id)
    nl_files = list_nl_files(base / "nl")
    if not nl_files:
        raise FileNotFoundError(f"no NL files under {base / 'nl'}")

    results: list[dict] = []
    out_dir = base / "yaml"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in nl_files:
        text = path.read_text(encoding="utf-8")
        state = compile_nl(
            text,
            req_id=req_id,
            nl_path=str(path),
            llm_profile=llm_profile,
            force_backend=force_backend,
        )
        out_path = out_dir / f"{_nl_stem(path)}.yaml"
        payload = {
            "ok": not state.get("errors"),
            "needs_review": bool(state.get("needs_review")),
            "backend": state.get("backend"),
            "nl": str(path),
            "out": str(out_path),
            "errors": state.get("errors") or [],
        }
        case = state.get("yaml_case") or {}
        if case and not state.get("errors"):
            case = _apply_skip_tags(case, text)
            with out_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(case, f, allow_unicode=True, sort_keys=False)
            # drop legacy *.compiled.yaml sibling if present
            legacy = out_dir / f"{_nl_stem(path)}.compiled.yaml"
            if legacy.is_file():
                legacy.unlink()
            payload["case_id"] = case.get("case_id")
            payload["needs_review"] = bool((case.get("meta") or {}).get("needs_review")) or payload[
                "needs_review"
            ]
        results.append(payload)
    return results
