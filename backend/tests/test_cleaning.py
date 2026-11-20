"""Cleaning admission, stage separation, UTC fidelity and portable inference."""

import inspect
import io

import joblib
import pandas as pd
import pytest


def cfg(*steps, **extra):
    return {"version": "cleaning-v1", "steps": list(steps), **extra}


def condition(name="x", value=0):
    return {
        "kind": "call",
        "operation": "less",
        "arguments": [{"kind": "reference", "name": name}, {"kind": "literal", "value": value}],
    }


def test_ordered_normalize_convert_replace_and_typed_validation():
    from mlstudio.cleaning_runtime_v1 import cleaning_transform, cleaning_validate

    config = cfg(
        {
            "id": "n",
            "kind": "normalize",
            "column": "x",
            "tokens": ["na"],
            "trim": True,
            "case_sensitive": False,
        },
        {
            "id": "c",
            "kind": "convert",
            "column": "x",
            "destination": "continuous",
            "invalid": "coerce",
        },
        {
            "id": "r",
            "kind": "replace",
            "column": "x",
            "match": "",
            "value": None,
            "condition": condition(),
        },
    )
    assert cleaning_validate(config, {"x": "string"})["x"] == "numeric"
    frame = pd.DataFrame({"x": [" NA ", "-1", "2", "oops"]})
    output, diagnostics = cleaning_transform(frame, config, diagnostic=True)
    assert output.x.isna().tolist() == [True, True, False, True]
    assert output.x.iloc[2] == 2
    assert diagnostics[1]["invalid_count"] == 1
    assert frame.x.iloc[0] == " NA "


def test_selection_order_unknown_missing_and_deduplication():
    from mlstudio.cleaning_runtime_v1 import cleaning_select

    frame = pd.DataFrame(
        {"x": [-1.0, None, 2.0, 2.0], "g": ["a", None, "b", "b"]}, index=[4, 3, 2, 1]
    )
    config = cfg(
        {"id": "f", "kind": "filter", "condition": condition(), "keep": "nonmatches"},
        {"id": "d", "kind": "deduplicate", "columns": ["x", "g"], "keep": "last"},
    )
    output, events = cleaning_select(frame, config)
    assert output.index.tolist() == [3, 1]
    assert [(e["before"], e["retained"], e["removed"]) for e in events] == [(4, 3, 1), (3, 2, 1)]
    only_missing, _ = cleaning_select(
        frame,
        cfg(
            {
                "id": "m",
                "kind": "missing_filter",
                "columns": ["x", "g"],
                "mode": "all",
                "keep": "missing",
            }
        ),
    )
    assert only_missing.index.tolist() == [3]


def test_datetime_fill_missing_only_invalid_and_nanosecond_utc():
    from mlstudio.cleaning_runtime_v1 import cleaning_transform

    frame = pd.DataFrame({"d": [None, "broken", "2020-01-01T01:00:00.123456789+01:00"]})
    config = cfg(
        {
            "id": "dt",
            "kind": "datetime_fill",
            "column": "d",
            "value": "2022-01-01",
            "policy": {"naive": "utc", "invalid": "coerce"},
        },
        input_types={"d": "datetime"},
    )
    output, diagnostics = cleaning_transform(frame, config, diagnostic=True)
    assert output.d.iloc[0] == "2022-01-01T00:00:00+00:00"
    assert pd.isna(output.d.iloc[1])
    assert output.d.iloc[2] == "2020-01-01T00:00:00.123456789+00:00"
    assert diagnostics[0]["invalid_count"] == 1
    config["steps"][0]["policy"]["invalid"] = "reject"
    with pytest.raises(ValueError, match="invalid"):
        cleaning_transform(frame, config)
    assert len(cleaning_transform(frame, config, diagnostic=True)[0]) == 3


def test_admission_rejects_leakage_wrong_types_and_bounded_trees():
    from mlstudio.cleaning_runtime_v1 import cleaning_validate
    from mlstudio.cleaning_schemas import CleaningConfig

    types = {"x": "numeric", "y": "numeric"}
    for step in [
        {"id": "r", "kind": "replace", "column": "x", "match": 1, "value": True},
        {"id": "d", "kind": "deduplicate", "columns": ["y"], "keep": "first"},
        {"id": "f", "kind": "filter", "condition": condition("y"), "keep": "matches"},
        {
            "id": "n",
            "kind": "normalize",
            "column": "x",
            "tokens": ["NA"],
            "trim": True,
            "case_sensitive": True,
        },
    ]:
        with pytest.raises(ValueError):
            cleaning_validate(cfg(step), types, "y")
    node = {"kind": "literal", "value": True}
    for _ in range(10):
        node = {"kind": "call", "operation": "not", "arguments": [node]}
    with pytest.raises(ValueError):
        CleaningConfig.model_validate(
            cfg({"id": "f", "kind": "filter", "condition": node, "keep": "matches"})
        )
    for value in [2**53, float("inf"), {}, [1]]:
        with pytest.raises(ValueError):
            CleaningConfig.model_validate(
                cfg({"id": "r", "kind": "replace", "column": "x", "value": value})
            )


def test_validation_and_conversion_never_drop_prediction_rows():
    from mlstudio.cleaning_runtime_v1 import CleaningFeatures, cleaning_transform

    frame = pd.DataFrame({"x": ["true", "false", "oops", None]})
    config = cfg(
        {"id": "b", "kind": "convert", "column": "x", "destination": "binary", "invalid": "coerce"},
        {"id": "d", "kind": "deduplicate", "columns": ["x"], "keep": "first"},
    )
    output = CleaningFeatures(config).fit_transform(frame)
    assert len(output) == 4
    assert str(output.x.dtype) == "boolean"
    assert output.x.isna().sum() == 2
    rule = cfg(
        {"id": "v", "kind": "validate", "column": "x", "check": "required", "action": "reject"}
    )
    with pytest.raises(ValueError, match="invalid"):
        cleaning_transform(output, rule)
    assert cleaning_transform(output, rule, diagnostic=True)[1][0]["invalid_count"] == 2


def test_standalone_helpers_and_joblib_roundtrip():
    import mlstudio.cleaning_runtime_v1 as runtime
    import mlstudio.derived_runtime_v1 as derived
    import mlstudio.temporal_runtime_v1 as temporal

    frame = pd.DataFrame({"x": [1.0, -1.0, None]})
    config = cfg(
        {"id": "r", "kind": "replace", "column": "x", "value": 0.0, "condition": condition()}
    )
    transformer = runtime.CleaningFeatures(config).fit(frame)
    buffer = io.BytesIO()
    joblib.dump(transformer, buffer)
    buffer.seek(0)
    pd.testing.assert_frame_equal(
        joblib.load(buffer).transform(frame), transformer.transform(frame)
    )
    namespace = {}
    source = "\n".join(inspect.getsource(module) for module in [derived, temporal, runtime])
    source = "\n".join(
        line for line in source.splitlines() if not line.startswith("from mlstudio.")
    )
    exec(compile(source, "<frozen-cleaning>", "exec"), namespace)
    pd.testing.assert_frame_equal(
        namespace["cleaning_transform"](frame, config)[0], transformer.transform(frame)
    )
