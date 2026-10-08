"""Unit-ish checks for YAML schema without browser."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from framework.paths import project_root
from framework.schema.case import UiCase
from framework.schema.loader import load_case


def test_load_demo_case():
    path = project_root() / "runs" / "DEMO-001" / "yaml" / "login_success.yaml"
    case = load_case(path)
    assert case.case_id == "TC_DEMO_AFTER_LOGIN_001"
    assert case.preconditions
    assert case.preconditions[0].auth == "logged_in"
    assert case.preconditions[0].account_ref == "default_tester"
    assert len(case.steps) >= 2
    assert case.steps[0].action.value == "open"
    assert case.base_url and "main.z-niu.com" in case.base_url


def test_step_requires_element_for_click():
    with pytest.raises(ValidationError):
        UiCase.model_validate(
            {
                "case_id": "X",
                "title": "bad",
                "steps": [{"action": "click"}],
            }
        )


def test_multi_select_and_assert_column_schema():
    case = UiCase.model_validate(
        {
            "case_id": "X",
            "title": "ok",
            "steps": [
                {"action": "multi_select", "element": "清洗次数", "value": "三次及以上"},
                {"action": "click_if_visible", "element": "展开筛选"},
                {"action": "assert_column", "element": "清洗次数", "expect": "gte:4"},
                {"action": "assert_options", "element": "清洗次数", "expect": "未清洗,首次清洗"},
            ],
        }
    )
    assert case.steps[0].action.value == "multi_select"
    with pytest.raises(ValidationError):
        UiCase.model_validate(
            {"case_id": "X", "title": "bad", "steps": [{"action": "assert_column", "element": "清洗次数"}]}
        )
