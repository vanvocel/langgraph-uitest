from framework.schema.case import ActionName, ObserveSpec, ToastExpect, UiCase
from framework.toast.observe import merge_observe


def _case() -> UiCase:
    return UiCase.model_validate(
        {
            "case_id": "X",
            "title": "t",
            "defaults": {
                "on_action": {
                    "observe": {"window_ms": 8000, "forbid_toast_levels": ["error"]}
                }
            },
            "steps": [{"action": "open", "url": "https://example.com/"}],
        }
    )


def test_open_without_step_observe_ignores_case_forbid():
    obs = merge_observe(_case(), None, ActionName.open)
    assert obs is None


def test_click_inherits_case_forbid_error():
    obs = merge_observe(_case(), None, ActionName.click)
    assert obs is not None
    assert "error" in (obs.forbid_toast_levels or [])


def test_click_if_visible_without_step_observe_ignores_case_forbid():
    obs = merge_observe(_case(), None, ActionName.click_if_visible)
    assert obs is None


def test_open_explicit_expect_toast_is_kept():
    step_obs = ObserveSpec(toasts=[ToastExpect(expect="error", contains="手机号或密码错误")])
    obs = merge_observe(_case(), step_obs, ActionName.open)
    assert obs is not None
    assert obs.toasts and obs.toasts[0].contains == "手机号或密码错误"
    assert not (obs.forbid_toast_levels or [])
