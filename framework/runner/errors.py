"""Failure classification for execution."""

from __future__ import annotations

from enum import Enum


class FailureCode(str, Enum):
    BIND_ERROR = "BIND_ERROR"
    ASSERT_FAIL = "ASSERT_FAIL"
    ENV_ERROR = "ENV_ERROR"
    UI_ERROR_TOAST = "UI_ERROR_TOAST"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNKNOWN = "UNKNOWN"


class StepError(Exception):
    def __init__(
        self,
        code: FailureCode,
        message: str,
        *,
        step_index: int | None = None,
        action: str | None = None,
        element: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.step_index = step_index
        self.action = action
        self.element = element
        self.expected = expected
        self.actual = actual
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "step_index": self.step_index,
            "action": self.action,
            "element": self.element,
            "expected": self.expected,
            "actual": self.actual,
            "details": self.details,
        }
