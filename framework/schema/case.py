"""Case YAML schema (Pydantic). Execution whitelist lives here."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ActionName(str, Enum):
    open = "open"
    click = "click"
    fill = "fill"
    select = "select"
    multi_select = "multi_select"
    hover = "hover"
    wait_visible = "wait_visible"
    click_if_visible = "click_if_visible"
    assert_visible = "assert_visible"
    assert_hidden = "assert_hidden"
    assert_text = "assert_text"
    assert_text_contains = "assert_text_contains"
    assert_value = "assert_value"
    assert_url = "assert_url"
    assert_url_contains = "assert_url_contains"
    assert_title = "assert_title"
    assert_count = "assert_count"
    assert_column = "assert_column"
    assert_options = "assert_options"
    clear_select = "clear_select"
    capture_column = "capture_column"
    assert_set = "assert_set"
    assert_set_disjoint = "assert_set_disjoint"
    assert_headers = "assert_headers"
    assert_filter_order = "assert_filter_order"
    assert_text_not_contains = "assert_text_not_contains"


class ToastExpect(BaseModel):
    expect: Literal["success", "error", "warning", "info"] | None = None
    forbid: Literal["success", "error", "warning", "info"] | None = None
    contains: str | None = None

    @model_validator(mode="after")
    def _one_of_expect_forbid(self) -> ToastExpect:
        if self.expect is None and self.forbid is None:
            raise ValueError("toast rule needs expect or forbid")
        return self


class NavigationObserve(BaseModel):
    expect_url: str | None = None
    expect_url_contains: str | None = None
    expect_element: str | None = None


class ObserveSpec(BaseModel):
    """Observation window after an action. Toast rules are schema-ready (Phase 3)."""

    window_ms: int = 5000
    toasts: list[ToastExpect] = Field(default_factory=list)
    forbid_toast_levels: list[str] | None = None
    navigation: NavigationObserve | None = None


class OnActionDefaults(BaseModel):
    observe: ObserveSpec | None = None


class CaseDefaults(BaseModel):
    on_action: OnActionDefaults | None = None


class Precondition(BaseModel):
    auth: Literal["logged_in"] | None = None
    account_ref: str | None = None

    model_config = {"extra": "allow"}


class Step(BaseModel):
    action: ActionName
    element: str | None = None
    value: str | None = None
    url: str | None = None
    expect: str | None = None
    timeout_ms: int | None = None
    observe: ObserveSpec | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _validate_by_action(self) -> Step:
        a = self.action
        if a == ActionName.open and not self.url and not self.value:
            raise ValueError("open requires url (or value as url)")
        if a in {
            ActionName.click,
            ActionName.fill,
            ActionName.select,
            ActionName.multi_select,
            ActionName.hover,
            ActionName.wait_visible,
            ActionName.click_if_visible,
            ActionName.assert_visible,
            ActionName.assert_hidden,
            ActionName.assert_text,
            ActionName.assert_text_contains,
            ActionName.assert_value,
            ActionName.assert_count,
            ActionName.assert_column,
            ActionName.assert_options,
            ActionName.clear_select,
            ActionName.capture_column,
            ActionName.assert_set,
            ActionName.assert_headers,
            ActionName.assert_text_not_contains,
        } and not self.element:
            raise ValueError(f"{a.value} requires element")
        if a in {ActionName.fill, ActionName.select, ActionName.multi_select} and self.value is None:
            raise ValueError(f"{a.value} requires value")
        if a == ActionName.capture_column and self.value is None:
            raise ValueError("capture_column requires value (variable name)")
        if a in {
            ActionName.assert_text,
            ActionName.assert_text_contains,
            ActionName.assert_text_not_contains,
            ActionName.assert_column,
            ActionName.assert_options,
            ActionName.assert_headers,
            ActionName.assert_filter_order,
            ActionName.assert_set,
        } and self.expect is None:
            raise ValueError(f"{a.value} requires expect")
        if a == ActionName.assert_set_disjoint and (not self.value or not self.expect):
            raise ValueError("assert_set_disjoint requires value and expect (variable names)")
        if a == ActionName.assert_count and self.expect is None and self.value is None:
            raise ValueError("assert_count requires expect or value (count)")
        if a in {ActionName.assert_url, ActionName.assert_url_contains, ActionName.assert_title}:
            if self.expect is None and self.value is None:
                raise ValueError(f"{a.value} requires expect or value")
        return self


class UiCase(BaseModel):
    case_id: str
    title: str
    requirement_id: str | None = None
    base_url: str | None = None
    preconditions: list[Precondition] = Field(default_factory=list)
    defaults: CaseDefaults | None = None
    steps: list[Step]
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _need_steps(self) -> UiCase:
        if not self.steps:
            raise ValueError("steps must not be empty")
        return self
