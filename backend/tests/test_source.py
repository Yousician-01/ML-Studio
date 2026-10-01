import numpy as np
import pandas as pd
import pytest

from mlstudio.services.source import DomainError, infer_semantic, json_scalar


@pytest.mark.parametrize(
    "name,values,expected",
    [
        ("measurement", [1.1, 2.3, 4.9], "continuous"),
        ("unique_float", [1.1, 2.3, 4.9, 5.2], "continuous"),
        ("record_id", [1001, 1002, 1003], "identifier"),
        ("record_id", [1.1, 2.3, 4.9], "continuous"),
        ("id", ["aa", "bb", "cc"], "identifier"),
        ("code", ["aa", "bb", "cc"], "categorical"),
        ("label", ["yes", "no", None], "binary"),
        ("date", ["2025-01-01", "2025-02-01", "2025-03-01"], "datetime"),
        ("integer_date", [20250101, 20250201, 20250301], "continuous"),
        ("date", ["2025-01-01", "not-date", "2025-03-01"], "categorical"),
        (
            "notes",
            ["This is a long sentence describing one customer in detail.", "short", "other"],
            "text",
        ),
        ("strings", [f"value-{index}" for index in range(25)], "text"),
        ("empty", [None, None, None], "unknown"),
        ("constant", [1, 1, None], "unknown"),
        ("with_missing", [1.1, None, 3.4, 7.9], "continuous"),
    ],
)
def test_explicit_inference_rules(name, values, expected):
    assert infer_semantic(pd.Series(values, name=name)) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (np.int64(5), 5),
        (np.float64(1.5), 1.5),
        (np.bool_(True), True),
        (np.nan, None),
        (pd.NA, None),
        ("yes", "yes"),
        (np.int64(9007199254740991), 9007199254740991),
        (np.int64(-9007199254740991), -9007199254740991),
        (np.int64(9007199254740992), {"value_type": "integer", "value": "9007199254740992"}),
        (np.int64(-9007199254740993), {"value_type": "integer", "value": "-9007199254740993"}),
    ],
)
def test_json_scalar_types(value, expected):
    result = json_scalar(value)
    assert result == expected
    assert type(result) is type(expected)


def test_json_scalar_rejects_infinity():
    with pytest.raises(DomainError):
        json_scalar(float("inf"))
