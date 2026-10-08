"""Project path helpers and settings loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    return ROOT


def runs_root() -> Path:
    return ROOT / "runs"


def req_dir(req_id: str) -> Path:
    return runs_root() / req_id


REQ_SUBDIRS = (
    "nl",
    "yaml",
    "pom",
    "bindings",
    "fixtures",
    "excel",
    "allure-results",
    "logs",
)


def init_requirement(req_id: str) -> Path:
    """Create runs/<req_id>/ directory tree. Returns the requirement path."""
    if not req_id or any(sep in req_id for sep in ("/", "\\", "..")):
        raise ValueError(f"invalid requirement id: {req_id!r}")

    base = req_dir(req_id)
    for name in REQ_SUBDIRS:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists() and name in {
            "nl",
            "yaml",
            "pom",
            "bindings",
            "logs",
            "fixtures",
            "excel",
        }:
            gitkeep.touch()
    return base


def load_settings() -> dict[str, Any]:
    path = ROOT / "config" / "settings.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
