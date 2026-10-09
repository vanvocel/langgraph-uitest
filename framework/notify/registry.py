"""Register and resolve notify channels."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from framework.notify.base import NotifyChannel

_FACTORIES: dict[str, Callable[[dict[str, Any]], NotifyChannel]] = {}


def register_channel(name: str, factory: Callable[[dict[str, Any]], NotifyChannel]) -> None:
    _FACTORIES[name] = factory


def known_channels() -> list[str]:
    return sorted(_FACTORIES)


def create_channel(name: str, config: dict[str, Any] | None = None) -> NotifyChannel:
    if name not in _FACTORIES:
        raise ValueError(f"unknown notify channel: {name!r}; known={known_channels()}")
    return _FACTORIES[name](dict(config or {}))


def _register_builtins() -> None:
    from framework.notify.channels.email import EmailChannel
    from framework.notify.channels.feishu import FeishuChannel
    from framework.notify.channels.wecom import WecomChannel

    register_channel("feishu", lambda cfg: FeishuChannel(cfg))
    register_channel("email", lambda cfg: EmailChannel(cfg))
    register_channel("wecom", lambda cfg: WecomChannel(cfg))


_register_builtins()
