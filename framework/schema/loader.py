"""Load and validate case YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from framework.schema.case import UiCase


def load_case(path: Path | str) -> UiCase:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"case YAML must be a mapping: {p}")
    return UiCase.model_validate(raw)


def list_case_files(yaml_dir: Path, *, include_manual: bool = False) -> list[Path]:
    """List runnable case YAML. Skip manual/AI-outbound/needs_fixture by default."""
    if not yaml_dir.is_dir():
        return []
    files = sorted(
        p
        for p in yaml_dir.iterdir()
        if p.suffix in {".yaml", ".yml"} and p.is_file() and ".compiled." not in p.name
    )
    if include_manual:
        return files
    runnable: list[Path] = []
    for path in files:
        try:
            case = load_case(path)
        except Exception:  # noqa: BLE001
            runnable.append(path)
            continue
        tags = {str(t).lower() for t in (case.tags or [])}
        meta = case.meta or {}
        if tags & {"manual", "ai_outbound", "needs_fixture"}:
            continue
        if meta.get("manual_only") or meta.get("needs_fixture"):
            continue
        runnable.append(path)
    return runnable
