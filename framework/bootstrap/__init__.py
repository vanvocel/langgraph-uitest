"""Bootstrap package: login and account resolution."""

__all__ = [
    "ensure_logged_in",
    "perform_ui_login",
    "resolve_account",
    "storage_state_for",
]


def __getattr__(name: str):
    if name in {"ensure_logged_in", "perform_ui_login", "storage_state_for"}:
        from framework.bootstrap import login as _login

        return getattr(_login, name)
    if name == "resolve_account":
        from framework.bootstrap.accounts import resolve_account

        return resolve_account
    raise AttributeError(name)
