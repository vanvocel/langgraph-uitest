"""Load LLM profile; keys come from environment variables."""

from __future__ import annotations

import os
from typing import Any, Literal

import yaml
from pydantic import BaseModel

from framework.paths import project_root


class LlmProfile(BaseModel):
    name: str
    provider: Literal["openai_compat"] = "openai_compat"
    model: str
    base_url: str
    api_key_env: str
    temperature: float = 0
    api_key: str = ""

    @property
    def has_key(self) -> bool:
        return bool(self.api_key.strip())


def load_llm_file() -> dict[str, Any]:
    path = project_root() / "config" / "llm.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def compile_backend() -> str:
    return str(load_llm_file().get("backend") or "stub").lower()


def resolve_profile(name: str | None = None) -> LlmProfile:
    raw = load_llm_file()
    profiles = raw.get("profiles") or {}
    chosen = name or os.getenv("LLM_PROFILE") or raw.get("active") or "deepseek"
    if chosen not in profiles:
        raise ValueError(f"unknown LLM profile: {chosen!r}; known={list(profiles)}")
    data = dict(profiles[chosen])
    env_name = data.get("api_key_env") or ""
    key = os.getenv(env_name, "").strip() if env_name else ""
    fields = {k: v for k, v in data.items() if k != "api_key"}
    return LlmProfile(name=chosen, api_key=key, **fields)
