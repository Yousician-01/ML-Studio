"""Bounded row-wise expression semantics and standalone transformer parity."""

import inspect

import numpy as np
import pandas as pd
import pytest


def col(name):
    return {"kind": "column", "name": name}


def ref(name):
    return {"kind": "reference", "name": name}


def lit(value):
    return {"kind": "literal", "value": value}


def call(operation, *arguments, **parameters):
    return dict(kind="call", operation=operation, arguments=list(arguments), parameters=parameters)


def cfg(**features):
    return dict(
        version="derived-v1", features=[dict(name=k, expression=v) for k, v in features.items()]
    )


def test_dependencies_strict_types_target_and_bounded_schema():
    from mlstudio.derived_schemas import DerivedConfig, validate_derived

    config = DerivedConfig.model_validate(
        cfg(
            ratio=call("safe_divide", ref("profit"), col("x")),
            profit=call("subtract", col("x"), lit(2)),
        )
    )
    order, types = validate_derived(config, {"x": "numeric"}, None)
    assert order == ["profit", "ratio"] and types == {"profit": "numeric", "ratio": "numeric"}
    for operation in ["greater", "greater_equal", "less", "less_equal"]:
        assert validate_derived(
            DerivedConfig.model_validate(cfg(a=call(operation, lit(1), lit(2)))), {}, None
        )[1] == {"a": "boolean"}
    with pytest.raises(ValueError, match="type|typed"):
        validate_derived(DerivedConfig.model_validate(cfg(a=lit(None))), {}, None)
    for expression in [call("add", col("s"), lit(1)), col("target"), ref("target"), ref("absent")]:
        with pytest.raises(ValueError):
            validate_derived(
                DerivedConfig.model_validate(cfg(a=expression)),
                {"s": "string", "target": "numeric"},
                "target",
            )
    with pytest.raises(ValueError, match="[Cc]ycl"):
        validate_derived(DerivedConfig.model_validate(cfg(a=ref("b"), b=ref("a"))), {}, None)
    expression = lit(1)
    for _ in range(20):
        expression = call("negate", expression)
    for value in [float("inf"), {}, [1], "x" * 5000]:
        with pytest.raises(ValueError):
            DerivedConfig.model_validate(cfg(a=lit(value)))
    with pytest.raises(ValueError, match="bounded|limit"):
        DerivedConfig.model_validate(cfg(a=expression))
    for value in [2**53, -(2**53)]:
        with pytest.raises(ValueError, match="Exact integer.*safe range"):
            DerivedConfig.model_validate(cfg(a=lit(value)))


def test_domain_counts_preserve_source_and_no_string_coercion():
    from mlstudio.derived_runtime_v1 import derived_transform

    source = pd.DataFrame({"x": [4.0, -1.0, None, 1e308], "y": [2.0, 0.0, 2.0, 1e-308]})
    output, counts = derived_transform(
        source,
        cfg(
            ratio=call("safe_divide", col("x"), col("y")),
            root=call("sqrt", col("x")),
            rounded=call("round", lit(2.5), precision=0),
        ),
    )
    pd.testing.assert_frame_equal(output[source.columns], source)
    assert output["ratio"].iloc[0] == 2 and output["ratio"].iloc[1:].isna().all()
    assert counts["ratio"] == {"invalid_count": 2, "missing_count": 3}
    assert counts["root"] == {"invalid_count": 1, "missing_count": 2}
    assert output["rounded"].tolist() == [2.0] * 4
    for dtype in [object, "int64", "Int64"]:
        adjacent = pd.DataFrame({"x": pd.Series([2**53, 2**53 + 1], dtype=dtype)})
        with pytest.raises(ValueError, match="Exact integer.*safe range"):
            derived_transform(
                adjacent,
                dict(cfg(a=call("equal", col("x"), lit(1))), input_types={"x": "numeric"}),
            )
    with pytest.raises(ValueError, match="Exact integer.*safe range"):
        derived_transform(source, cfg(a=call("equal", lit(2**53 + 1), lit(1))))
    with pytest.raises(ValueError):
        derived_transform(
            pd.DataFrame({"x": ["secret"]}),
            dict(cfg(a=call("sqrt", col("x"))), input_types={"x": "numeric"}),
        )


def test_nullable_logic_if_strings_and_temporal_inputs():
    from mlstudio.derived_runtime_v1 import derived_transform
    from mlstudio.derived_schemas import DerivedConfig, validate_derived

    config = cfg(
        both=call("and", col("flag"), lit(False)),
        either=call("or", col("flag"), lit(True)),
        choice=call("if", col("flag"), lit("yes"), lit("no")),
        clean=call("replace", call("trim", col("s")), lit("."), lit("!")),
        fallback=call("coalesce", col("s"), lit("unknown")),
        contains=call("contains", col("s"), lit(".")),
        years=call("safe_divide", ref("days"), lit(365.25)),
    )
    _, types = validate_derived(
        DerivedConfig.model_validate(config),
        {"flag": "boolean", "s": "string"},
        None,
        {"days": "numeric"},
    )
    config["input_types"] = {"flag": "boolean", "s": "string", "days": "numeric"}
    config["output_types"] = types
    source = pd.DataFrame(
        {"flag": [True, False, None], "s": [" a.b ", "xx", None], "days": [365.25, 0.0, None]}
    )
    from types import SimpleNamespace

    from mlstudio.services.derived import source_types

    metadata = SimpleNamespace(
        columns=[
            {"name": name, "inferred_semantic_type": semantic, "semantic_override": None}
            for name, semantic in [
                ("flag", "binary"),
                ("s", "categorical"),
                ("days", "categorical"),
            ]
        ]
    )
    assert source_types(metadata, source) == {"flag": "boolean", "s": "string", "days": "numeric"}
    output, _ = derived_transform(source, config)
    assert output["both"].tolist() == [0.0, 0.0, 0.0]
    assert output["either"].tolist() == [1.0, 1.0, 1.0]
    assert output["choice"].iloc[:2].tolist() == ["yes", "no"] and pd.isna(output["choice"].iloc[2])
    assert output["clean"].iloc[0] == "a!b" and output["contains"].iloc[:2].tolist() == [1.0, 0.0]
    assert output["fallback"].iloc[2] == "unknown" and output["years"].iloc[0] == 1
    assert output["choice"].dtype == object and output["both"].dtype == np.dtype("float64")


def test_transformer_standalone_and_pickle(tmp_path):
    import joblib

    from mlstudio import derived_runtime_v1
    from mlstudio.codegen.render import template_parts

    config = cfg(a=call("add", col("x"), lit(2)))
    source = pd.DataFrame({"x": [1.0, np.nan]})
    transformer = derived_runtime_v1.DerivedFeatures(config).fit(source)
    imports, functions = template_parts(inspect.getsource(derived_runtime_v1))
    namespace = {}
    exec("\n\n".join([*imports, *functions]), namespace)
    pd.testing.assert_frame_equal(
        transformer.transform(source), namespace["DerivedFeatures"](config).fit_transform(source)
    )
    path = tmp_path / "derived.joblib"
    joblib.dump(transformer, path)
    pd.testing.assert_frame_equal(
        transformer.transform(source), joblib.load(path).transform(source)
    )
    assert transformer.get_feature_names_out().tolist() == ["x", "a"]


def test_string_limits_empty_frames_and_declared_column_order():
    from mlstudio.derived_runtime_v1 import DerivedFeatures, derived_transform

    config = cfg(
        joined=call("concat", lit("a"), lit("b"), lit("c")),
        text=call("replace", col("s"), lit(""), lit("x" * 1000)),
    )
    output, counts = derived_transform(pd.DataFrame({"s": [None, "hello"]}), config)
    assert output["joined"].tolist() == ["abc", "abc"]
    assert output["text"].isna().all() and counts["text"]["invalid_count"] == 1
    empty, _ = derived_transform(pd.DataFrame({"s": pd.Series([], dtype=object)}), config)
    assert empty.empty
    config = cfg(b=call("add", ref("a"), lit(1)), a=lit(1))
    transformer = DerivedFeatures(config).fit(pd.DataFrame({"x": [1]}))
    assert (
        transformer.transform(pd.DataFrame({"x": [1]})).columns.tolist()
        == transformer.get_feature_names_out().tolist()
    )
