from framework.runner.errors import StepError
from framework.tools.actions import check_column_values, evaluate_column_expect, parse_column_rule


def test_parse_column_rule():
    assert parse_column_rule("gte:4") == ("gte", [4])
    assert parse_column_rule("3") == ("eq", [3])
    assert parse_column_rule("in:1,3,4") == ("in", [1, 3, 4])


def test_check_column_values_pass_and_fail():
    check_column_values([4, 5, 9], "gte", [4])
    check_column_values([1, 3, 1], "in", [1, 3])
    evaluate_column_expect(["1", "3", "8"], "union:1,3,>=4")
    evaluate_column_expect(["人工导入 / 经销商"], "contains:人工导入")
    try:
        check_column_values([0, 1], "eq", [0])
        raise AssertionError("expected fail")
    except StepError:
        pass
    try:
        check_column_values([], "eq", [0])
        raise AssertionError("expected fail")
    except StepError:
        pass
