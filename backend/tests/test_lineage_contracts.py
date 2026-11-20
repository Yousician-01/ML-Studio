"""Computed lineage and portable schema boundaries, not another execution engine."""

import numpy as np
import pandas as pd
import pytest


def payload():
    return {
        "target": {"column": "label"},
        "features": {"x": {"included": False}, "capped": {"included": True}},
        "derived": {"features": [{"name": "twice", "expression": {"kind": "column", "name": "x"}}]},
        "feature_engineering": {
            "features": [{"name": "logged", "source": "twice", "method": "log1p"}]
        },
        "outlier_treatment": {
            "features": [{"name": "capped", "source": "logged", "indicator": "flag"}]
        },
    }


def columns():
    return [
        {"name": "x", "physical_dtype": "float64", "effective_semantic_type": "continuous"},
        {"name": "label", "physical_dtype": "str", "effective_semantic_type": "binary"},
        {"name": "unused", "physical_dtype": "str", "effective_semantic_type": "text"},
    ]


def test_registry_tracks_transitive_inputs_without_requiring_label_or_unused_source():
    from mlstudio.lineage import registry

    evidence = registry(payload(), columns())
    assert not evidence["issues"]
    nodes = {f["name"]: f for f in evidence["features"]}
    assert nodes["capped"]["ancestors"] == ["x", "twice", "logged"]
    assert nodes["capped"]["requires_fit"] and nodes["x"]["inference_required"]
    assert nodes["x"]["dependents"] == ["twice", "logged", "capped", "flag"]
    assert [c["name"] for c in evidence["raw_inputs"]] == ["x"]


def test_registry_reports_missing_collision_cycle_and_stage_errors():
    from mlstudio.lineage import registry

    for mutation, expected in [
        (
            lambda p: p["derived"]["features"][0].update(
                expression={"kind": "reference", "name": "absent"}
            ),
            "reference_missing",
        ),
        (lambda p: p["derived"]["features"][0].update(name="x"), "output_collision"),
        (
            lambda p: p["derived"]["features"][0].update(
                expression={"kind": "reference", "name": "twice"}
            ),
            "dependency_cycle",
        ),
        (
            lambda p: p["derived"]["features"][0].update(
                expression={"kind": "reference", "name": "capped"}
            ),
            "stage_dependency",
        ),
    ]:
        p = payload()
        mutation(p)
        assert expected in {i["code"] for i in registry(p, columns())["issues"]}


def test_target_leakage_and_selection_only_raw_dependencies():
    from mlstudio.lineage import registry

    for field in ["feature_engineering", "outlier_treatment"]:
        p = payload()
        p[field]["features"][0]["source"] = "label"
        assert "target_leakage" in {i["code"] for i in registry(p, columns())["issues"]}
    p = payload()
    p["cleaning"] = {"steps": [{"id": "rows", "kind": "missing_filter", "columns": ["unused"]}]}
    assert "unused" not in [c["name"] for c in registry(p, columns())["raw_inputs"]]
    p["imputation"] = {"columns": {"x": {"rules": [{"group_by": ["label"]}]}}}
    assert "target_leakage" in {i["code"] for i in registry(p, columns())["issues"]}


def test_raw_guard_projects_extras_before_derivation_and_leaves_cleaning_values_intact():
    from mlstudio.schema_runtime_v1 import RawInputs

    guard = RawInputs({"version": "schema-contract-v1", "raw_inputs": [{"name": "x"}]})
    raw = pd.DataFrame(
        {"x": ["NA", " 3 "], "derived_shadow": [8, 9], "label": [0, 1]}, index=[9, 2]
    )
    result = guard.fit_transform(raw)
    assert result.columns.tolist() == ["x"] and result.x.tolist() == ["NA", " 3 "]
    assert result.index.tolist() == [9, 2]
    # sklearn must recognize a fitted prefix containing only the raw schema guard.
    from sklearn.pipeline import Pipeline

    pd.testing.assert_frame_equal(Pipeline([("raw_schema", guard)]).transform(raw), result)
    with pytest.raises(ValueError, match="x"):
        guard.transform(raw.drop(columns="x"))
    with pytest.raises(ValueError, match="unique"):
        guard.transform(pd.DataFrame([[1, 2]], columns=["x", "x"]))


def test_estimator_contract_freezes_names_count_mask_and_numeric_validation():
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder

    from mlstudio.schema_runtime_v1 import ContractPreprocessor

    frame = pd.DataFrame({"x": [1.0, 2.0], "cat": ["a", "b"]})
    guard = ContractPreprocessor(
        ColumnTransformer(
            [
                ("x", "passthrough", ["x"]),
                ("category", OneHotEncoder(handle_unknown="ignore"), ["cat"]),
            ]
        )
    )
    matrix = guard.fit_transform(frame)
    assert guard.contract_["feature_count"] == matrix.shape[1] == 3
    assert guard.contract_["feature_names"] == ["x__x", "category__cat_a", "category__cat_b"]
    assert guard.transform(pd.DataFrame({"cat": ["new"], "x": [3.0]})).shape == (1, 3)
    with pytest.raises(ValueError, match="nonfinite|missing"):
        guard.transform(pd.DataFrame({"x": [np.inf], "cat": ["a"]}))
    guard.contract_["feature_names"].reverse()
    with pytest.raises(ValueError, match="order"):
        guard.transform(frame)


def test_stateless_engineering_chains_are_sequential_and_fitted_chains_rejected():
    from mlstudio.feature_engineering_runtime_v1 import EngineeringFeatures, engineering_validate
    from mlstudio.feature_engineering_schemas import EngineeringConfig

    config = EngineeringConfig(
        features=[
            {"name": "logged", "source": "x", "method": "log1p"},
            {"name": "root", "source": "logged", "method": "sqrt"},
        ]
    ).model_dump(mode="json")
    engineering_validate(config, {"x": "numeric"})
    result = EngineeringFeatures(config).fit_transform(pd.DataFrame({"x": [1.0, 2.0, 4.0]}))
    np.testing.assert_allclose(result.root, np.sqrt(np.log1p([1, 2, 4])))
    for bad in [
        list(reversed(config["features"])),
        [{"name": "logged", "source": "x", "method": "quantile"}, config["features"][1]],
    ]:
        with pytest.raises(ValueError):
            engineering_validate({"features": bad}, {"x": "numeric"})


def test_new_contract_source_is_portable_for_all_tasks_and_historical_plans_omit_it(
    tmp_path, monkeypatch
):
    from test_outliers_selection import (
        test_three_task_generated_execution_and_fresh_process_inference,
    )

    import mlstudio.codegen.dispatch as dispatch

    original = dispatch.generate_for_version
    import mlstudio.pipeline_schemas as schemas

    original_load = schemas.load_ir

    def add_chain(body, task):
        body["feature_engineering"]["features"].extend(
            [
                {"name": "log_root", "source": "logged", "method": "sqrt"},
                {"name": "root_quantile", "source": "log_root", "method": "quantile"},
            ]
        )
        for name in ["log_root", "root_quantile"]:
            body["features"][name] = {
                "included": True,
                "operations": [{"type": "impute", "strategy": "median"}],
            }
        return original_load(body, task)

    monkeypatch.setattr(schemas, "load_ir", add_chain)

    def generate(plan):
        source = original(plan)
        assert "schema-contract-v1" in source and "ContractPreprocessor" in source
        return source

    monkeypatch.setattr(dispatch, "generate_for_version", generate)
    test_three_task_generated_execution_and_fresh_process_inference(tmp_path, monkeypatch)


def test_registry_api_preserves_saved_ir_and_exposes_structured_target_errors(client):
    from test_projects_datasets import configure, create, upload

    project = create(client)
    upload(client, project, b"x,unused,label\n,a,yes\n2,b,no\n4,c,yes\n8,d,no\n")
    configure(client, project, target_column="label")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    ir = state["ir"]
    ir["derived"] = {
        "version": "derived-v1",
        "features": [
            {
                "name": "twice",
                "expression": {
                    "kind": "call",
                    "operation": "multiply",
                    "arguments": [{"kind": "column", "name": "x"}, {"kind": "literal", "value": 2}],
                    "parameters": {},
                },
            }
        ],
    }
    ir["feature_engineering"] = {
        "version": "feature-engineering-v1",
        "features": [
            {"name": "logged", "source": "twice", "method": "log1p"},
            {"name": "root", "source": "logged", "method": "sqrt"},
        ],
    }
    ir["features"] = {
        name: {"included": name == "root", "operations": []}
        for name in ["x", "unused", "twice", "logged", "root"]
    }
    saved = client.patch(path, json={"revision": state["revision"], "ir": ir})
    assert saved.status_code == 200, saved.text
    evidence = saved.json()["lineage"]
    assert not evidence["issues"]
    assert [c["name"] for c in evidence["raw_inputs"]] == ["x"]
    assert client.get(path).json()["ir"] == saved.json()["ir"]
    ir["feature_engineering"]["features"][0]["source"] = "label"
    bad = client.patch(path, json={"revision": saved.json()["revision"], "ir": ir}).json()
    assert any(i["code"] == "target_leakage" and i["column"] == "logged" for i in bad["issues"])
    assert not bad["code_generation_ready"]
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.feature_engineering import upstream_imputation

    current = saved.json()["ir"]
    current["imputation"] = {
        "version": "imputation-v1",
        "columns": {
            "x": {
                "rules": [{"strategy": "median"}],
                "fallback": {"strategy": "constant", "value": 1},
            }
        },
    }
    current["feature_engineering"]["features"][0]["source"] = "x"
    typed = load_ir(current, "binary_classification")
    assert (
        upstream_imputation(
            typed, "root", {"root": {"invalid_count": 0}, "logged": {"invalid_count": 0}}
        )
        is not None
    )
    assert upstream_imputation(typed, "root", {"logged": {"invalid_count": 1}}) is None

    current["model"] = {"type": "logistic_regression"}
    current["split"] = {}
    checked = client.patch(path, json={"revision": bad["revision"], "ir": current}).json()
    assert not any(
        i["code"] in {"feature_missing_values", "feature_all_missing"} and i["column"] == "root"
        for i in checked["issues"]
    )
