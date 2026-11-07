"""Bounded selective imputation, training isolation and portable inference."""

import inspect
import io
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
import pytest


def config(rules=None, fallback=None, **extra):
    return {
        "version": "imputation-v1",
        "columns": {
            "x": {
                "rules": rules or [{"strategy": "median", "group_by": ["g"]}],
                "fallback": fallback or {"strategy": "constant", "value": -1},
                **extra,
            }
        },
    }


def test_validation_types_references_and_label_exclusion():
    from mlstudio.imputation_schemas import ImputationConfig, validate_imputation

    types = {"x": "numeric", "g": "string", "flag": "boolean", "label": "numeric"}
    condition = {
        "kind": "call",
        "operation": "equal",
        "arguments": [{"kind": "reference", "name": "g"}, {"kind": "literal", "value": "a"}],
    }
    validate_imputation(
        ImputationConfig.model_validate(config([{"strategy": "mean", "condition": condition}])),
        types,
        "label",
    )
    for bad in [
        config(indicator="g"),
        config([{"strategy": "mean", "group_by": ["x"]}]),
        config([{"strategy": "mean", "group_by": ["label"]}]),
        config([{"strategy": "constant", "value": True}]),
    ]:
        with pytest.raises(ValueError):
            validate_imputation(ImputationConfig.model_validate(bad), types, "label")
    for name in ["absent", "label", "flag"]:
        bad = config(
            [
                {
                    "strategy": "mean",
                    "condition": {
                        "kind": "call",
                        "operation": "equal",
                        "arguments": [
                            {"kind": "reference", "name": name},
                            {"kind": "literal", "value": 1},
                        ],
                    },
                }
            ]
        )
        with pytest.raises(ValueError):
            validate_imputation(ImputationConfig.model_validate(bad), types, "label")
    for value in [float("inf"), 2**53, {}, [1]]:
        with pytest.raises(ValueError):
            ImputationConfig.model_validate(config([{"strategy": "constant", "value": value}]))
    condition = {"kind": "literal", "value": True}
    for _ in range(6):
        condition = {"kind": "call", "operation": "and", "arguments": [condition, condition]}
    bounded = {
        "columns": {
            name: {"rules": [{"strategy": "mean", "condition": condition} for _ in range(count)]}
            for name, count in [("x", 16), ("y", 16), ("z", 1)]
        }
    }
    with pytest.raises(ValueError, match="total.*predicate|predicate.*total"):
        ImputationConfig.model_validate(bounded)
    from mlstudio.imputation_runtime_v1 import validate_imputation as runtime_validate

    with pytest.raises(ValueError, match="total.*predicate|predicate.*total"):
        runtime_validate(bounded, {name: "numeric" for name in bounded["columns"]})


def test_ordered_group_rules_original_conditions_indicators_and_modes():
    from mlstudio.imputation_runtime_v1 import ImputationFeatures, imputation_diagnostics

    frame = pd.DataFrame({"x": [2.0, 8.0, np.nan, np.nan, np.nan], "g": ["a", "a", "a", "b", None]})
    rules = [
        {"strategy": "median", "group_by": ["g"]},
        {
            "strategy": "constant",
            "value": 7,
            "condition": {
                "kind": "call",
                "operation": "equal",
                "arguments": [{"kind": "column", "name": "g"}, {"kind": "literal", "value": "b"}],
            },
        },
    ]
    cfg = config(rules, indicator="x_missing")
    result = ImputationFeatures(cfg).fit_transform(frame)
    assert result.x.tolist() == [2, 8, 5, 7, -1]
    assert result.x_missing.tolist() == [0, 0, 1, 1, 1]
    assert frame.x.isna().sum() == 3
    assert imputation_diagnostics(frame, cfg)["x"] == {
        "missing_count": 3,
        "rule_matches": [3, 1],
        "indicator_values": [0.0, 0.0, 1.0, 1.0, 1.0],
    }
    for values, expected in [(["z", "a", None], "a"), ([True, False, None], False)]:
        categorical = pd.DataFrame({"x": values})
        mode = config([{"strategy": "most_frequent"}], {"strategy": "leave_missing"})
        assert ImputationFeatures(mode).fit_transform(categorical).x.iloc[-1] == expected
    numeric_category = pd.DataFrame({"x": pd.Categorical([4, 2, None])})
    assert ImputationFeatures(mode).fit_transform(numeric_category).x.iloc[-1] == 2
    # Predicates see original values even after another column was imputed.
    snapshot = config(
        [
            {
                "strategy": "constant",
                "value": 42,
                "condition": {
                    "kind": "call",
                    "operation": "is_missing",
                    "arguments": [{"kind": "reference", "name": "g"}],
                },
            }
        ]
    )
    snapshot["columns"] = {
        "g": {
            "rules": [{"strategy": "constant", "value": "filled"}],
            "fallback": {"strategy": "constant", "value": "filled"},
        },
        **snapshot["columns"],
    }
    assert ImputationFeatures(snapshot).fit_transform(frame).x.iloc[-1] == 42
    # Donors include observed values outside the recipient predicate.
    restricted = config([{"strategy": "mean", "condition": rules[1]["condition"]}])
    assert ImputationFeatures(restricted).fit_transform(frame).x.iloc[3] == 5


def test_training_only_unseen_missing_groups_and_bounds():
    from mlstudio.imputation_runtime_v1 import ImputationFeatures

    train = pd.DataFrame({"x": [1.0, 3.0, 100.0], "g": ["a", "a", "b"]})
    transformer = ImputationFeatures(config(fallback={"strategy": "mean"})).fit(train)
    unseen = pd.DataFrame({"x": [np.nan, np.nan, np.nan, 9999.0], "g": ["a", "unseen", None, "a"]})
    assert transformer.transform(unseen).x.tolist() == [2.0, 104 / 3, 104 / 3, 9999.0]
    with pytest.raises(ValueError, match="constant fallback"):
        ImputationFeatures(config(fallback={"strategy": "leave_missing"})).fit(
            pd.DataFrame({"x": [np.nan], "g": ["a"]})
        )
    bounded = pd.DataFrame({"x": np.ones(10001), "g": np.arange(10001)})
    with pytest.raises(ValueError, match="group.*limit"):
        ImputationFeatures(config()).fit(bounded)
    with pytest.raises(ValueError, match="Total.*group.*limit"):
        ImputationFeatures(config([{"strategy": "mean", "group_by": ["g"]} for _ in range(6)])).fit(
            bounded.head(9000)
        )
    with pytest.raises(ValueError, match="remaining missing|remain missing"):
        ImputationFeatures(config(fallback={"strategy": "leave_missing"})).fit(train).transform(
            unseen
        )


def test_generated_helpers_and_joblib_parity(tmp_path):
    from mlstudio import derived_runtime_v1, imputation_runtime_v1
    from mlstudio.codegen.render import template_parts

    source = (
        inspect.getsource(derived_runtime_v1)
        + "\n"
        + inspect.getsource(imputation_runtime_v1).replace(
            "from mlstudio.derived_runtime_v1 import derived_transform, derived_validate", ""
        )
    )
    imports, helpers = template_parts(source)
    namespace = {}
    exec("\n".join([*imports, *helpers]), namespace)
    train = pd.DataFrame({"x": [2.0, 4.0, np.nan], "g": ["a", "a", "a"]})
    actual = imputation_runtime_v1.ImputationFeatures(config()).fit(train)
    generated = namespace["ImputationFeatures"](config()).fit(train)
    pd.testing.assert_frame_equal(actual.transform(train), generated.transform(train))
    buffer = io.BytesIO()
    joblib.dump(actual, buffer)
    buffer.seek(0)
    pd.testing.assert_frame_equal(actual.transform(train), joblib.load(buffer).transform(train))
    # A fresh process has no backend imports: register embedded helpers, then unpickle.
    model = tmp_path / "imputer.joblib"
    joblib.dump(actual, model)
    script = tmp_path / "standalone.py"
    script.write_text(
        "\n".join(
            [
                "import sys",
                "class BlockBackend:",
                "    def find_spec(self, fullname, path=None, target=None):",
                "        if fullname.startswith('mlstudio'): raise ImportError('backend blocked')",
                "sys.meta_path.insert(0, BlockBackend())",
                *imports,
                *helpers,
                "ImputationFeatures = register_imputation_transformer()",
                "import joblib",
                "model = joblib.load(sys.argv[1])",
                "frame = pd.DataFrame({'x': [np.nan], 'g': ['a']})",
                "assert model.transform(frame).x.tolist() == [3.0]",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, str(script), str(model)], check=True, capture_output=True, text=True
    )
