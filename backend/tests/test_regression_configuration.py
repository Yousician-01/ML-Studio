"""Regression readiness and model/split configuration contracts."""

import json
from copy import deepcopy
from uuid import uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_projects_datasets import configure, upload
from test_task_targets import regression

from mlstudio.main import create_app
from mlstudio.pipeline_schemas import RegressionPipelineIR
from mlstudio.services.train_validation import train_issues


def intent(model="linear_regression", parameters=None, split=None):
    return RegressionPipelineIR.model_validate(
        {
            "ir_version": "0.2",
            "task": "regression",
            "model": {"type": model, "parameters": parameters or {}},
            "split": {} if split is None else split,
        }
    )


def setup(client, data=None):
    project = regression(client)
    data = data or ("x,y\n" + "\n".join(f"{i},{i * 0.7}" for i in range(20))).encode()
    dataset = upload(client, project, data).json()
    assert configure(client, project, target_column="y").status_code == 200
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["model"] = {"type": "linear_regression"}
    state["ir"]["split"] = {}
    return project, dataset, path, state


def save(client, path, state):
    return client.patch(path, json={"revision": state["revision"], "ir": state["ir"]})


@pytest.mark.parametrize("model", ["linear_regression", "ridge"])
def test_complete_regression_configuration_metadata_persistence_and_review_guard(
    client, settings, model
):
    project, _, path, state = setup(client)
    state["ir"]["model"] = {"type": model}
    response = save(client, path, state)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["configuration_ready"] and state["prepare_valid"]
    assert state["code_generation_ready"] and not state["executable"]
    assert (state["eligible_rows"], state["train_rows"], state["test_rows"]) == (20, 16, 4)
    assert [d["id"] for d in state["model_catalogue"]] == ["linear_regression", "ridge"]
    assert all(d["task"] == "regression" for d in state["model_catalogue"])
    assert "stratify" not in state["ir"]["split"] and state["target_classes"] == []
    assert client.get(path).json() == state
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path).json() == state
    assert client.get(f"/api/v1/projects/{project['id']}/code").json()["ready"]
    run = client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={
            "request_id": str(uuid4()),
            "expected_revision": state["revision"],
            "expected_source_sha256": "sha256:" + "0" * 64,
            "expected_plan_sha256": "sha256:" + "0" * 64,
        },
    )
    assert run.status_code == 409 and "Refresh Code" in run.json()["detail"]


@pytest.mark.parametrize(
    "model,parameters",
    [
        ("linear_regression", {"fit_intercept": False}),
        ("ridge", {"alpha": 0, "fit_intercept": False}),
        ("ridge", {"alpha": 2.5}),
    ],
)
def test_valid_regression_parameters(model, parameters):
    ir = intent(model, parameters)
    for name, value in parameters.items():
        assert getattr(ir.model.parameters, name) == value


@pytest.mark.parametrize(
    "model,parameters",
    [
        ("linear_regression", {"fit_intercept": 1}),
        ("linear_regression", {"fit_intercept": "true"}),
        ("linear_regression", {"fit_intercept": None}),
        ("linear_regression", {"alpha": 1}),
        ("ridge", {"alpha": -0.001}),
        ("ridge", {"alpha": float("nan")}),
        ("ridge", {"alpha": float("inf")}),
        ("ridge", {"alpha": "1"}),
        ("ridge", {"alpha": True}),
        ("ridge", {"alpha": None}),
        ("ridge", {"fit_intercept": 0}),
        ("ridge", {"solver": "auto"}),
    ],
)
def test_strict_regression_parameters(model, parameters):
    with pytest.raises(ValidationError):
        intent(model, parameters)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("test_size", 0.049, "test_size_invalid"),
        ("test_size", 0.501, "test_size_invalid"),
        ("test_size", None, "test_size_invalid"),
        ("random_seed", -1, "seed_invalid"),
        ("random_seed", 2147483648, "seed_invalid"),
        ("random_seed", None, "seed_invalid"),
    ],
)
def test_invalid_split_is_saveable_contextual_intent(client, field, value, code):
    _, _, path, state = setup(client)
    state["ir"]["split"] = {field: value}
    response = save(client, path, state)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["ir"]["split"][field] == value and not result["configuration_ready"]
    issue = next(i for i in result["issues"] if i["code"] == code)
    assert issue["scope"] == "train" and issue["field"] == f"split.{field}"


@pytest.mark.parametrize("fraction,seed", [(0.05, 0), (0.5, 2147483647)])
def test_valid_split_bounds_and_missing_rows_excluded(fraction, seed):
    ir = intent(split={"test_size": fraction, "random_seed": seed})
    issues = train_issues(ir, pd.Series(list(range(20)) + [None] * 7))
    assert all(issue.severity == "non_blocking" for issue in issues)
    assert [issue.code for issue in issues] == (["r2_test_rows"] if fraction == 0.05 else [])


@pytest.mark.parametrize(
    "count,fraction,blocking,r2_warning",
    [
        (0, 0.2, True, True),
        (1, 0.2, True, True),
        (2, 0.2, True, True),
        (3, 0.2, False, True),
        (3, 0.5, True, False),
        (4, 0.5, False, False),
    ],
)
def test_small_split_and_r2_population(count, fraction, blocking, r2_warning):
    issues = train_issues(intent(split={"test_size": fraction}), pd.Series(range(count)))
    assert any(i.code == "split_training_rows" for i in issues) == blocking
    assert (
        any(i.code == "r2_test_rows" and i.severity == "non_blocking" for i in issues) == r2_warning
    )


def test_constant_and_partially_missing_target_are_configuration_ready(client):
    _, _, path, state = setup(client, b"x,y\n1,7\n2,7\n3,7\n4,7\n5,\n")
    state["ir"]["split"] = {"test_size": 0.5}
    response = save(client, path, state).json()
    assert response["configuration_ready"]
    assert (
        response["eligible_rows"],
        response["target_missing_count"],
        response["train_rows"],
        response["test_rows"],
    ) == (4, 1, 2, 2)
    assert any(
        i["code"] == "r2_constant_target" and i["severity"] == "non_blocking"
        for i in response["issues"]
    )


@pytest.mark.parametrize(
    "mutation,code,field",
    [
        (lambda ir: ir.update(model=None), "model_missing", "model"),
        (lambda ir: ir.update(split=None), "split_missing", "split"),
        (lambda ir: ir.update(target=None), "target_missing", "target.column"),
        (lambda ir: ir["features"]["x"].update(included=False), "features_empty", "features"),
        (
            lambda ir: ir["features"]["x"].update(
                operations=[{"type": "encode", "method": "one_hot"}]
            ),
            "operation_incompatible",
            "features.x.operations",
        ),
    ],
)
def test_incremental_invalid_intent_and_contextual_issue_locations(client, mutation, code, field):
    _, _, path, state = setup(client)
    mutation(state["ir"])
    response = save(client, path, state)
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result["configuration_ready"]
    issue = next(i for i in result["issues"] if i["code"] == code)
    assert issue["field"] == field
    assert client.get(path).json()["ir"] == result["ir"]


def test_stale_binding_retains_config_and_does_not_count_new_source(client):
    project, dataset, path, state = setup(client)
    state = save(client, path, state).json()
    original = deepcopy(state["ir"])
    upload(client, project, b"x,y\n1,4\n2,5\n3,6", expected=dataset["id"])
    stale = client.get(path).json()
    assert stale["stale"] and stale["ir"] == original and not stale["configuration_ready"]
    assert (
        stale["eligible_rows"] == 0 and stale["train_rows"] is None and stale["test_rows"] is None
    )
    assert next(i for i in stale["issues"] if i["code"] == "dataset_stale")["field"] == "dataset"


@pytest.mark.parametrize("alpha", ["-1", "1e309", "-1e309", "NaN"])
def test_invalid_alpha_api_returns_json_error_location_and_preserves_intent(client, alpha):
    _, _, path, state = setup(client)
    before = client.get(path).json()
    state["ir"]["model"] = {"type": "ridge", "parameters": {"alpha": "REPLACE"}}
    body = json.dumps({"revision": state["revision"], "ir": state["ir"]}).replace(
        '"REPLACE"', alpha
    )
    response = client.patch(path, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert any(error["loc"][-1] == "alpha" for error in response.json()["detail"])
    assert client.get(path).json() == before


def test_validation_never_fits_or_samples(client, monkeypatch):
    import sklearn.model_selection
    import sklearn.pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.preprocessing import StandardScaler

    def forbidden(*args, **kwargs):
        raise AssertionError("Configuration must not fit transformers/models or sample rows")

    monkeypatch.setattr(sklearn.pipeline.Pipeline, "fit", forbidden)
    monkeypatch.setattr(sklearn.model_selection, "train_test_split", forbidden)
    for learner in (SimpleImputer, StandardScaler, LinearRegression, Ridge):
        monkeypatch.setattr(learner, "fit", forbidden)
    _, _, path, state = setup(client)
    state["ir"]["features"]["x"]["operations"] = [{"type": "scale", "method": "standard"}]
    response = save(client, path, state)
    assert response.status_code == 200 and response.json()["configuration_ready"]


@pytest.mark.parametrize(
    "task,model", [("regression", "decision_tree"), ("binary_classification", "ridge")]
)
def test_task_model_mixing_is_rejected(client, task, model):
    project = client.post(
        "/api/v1/projects",
        json={
            "name": "Task",
            "problem_statement": "Predict",
            "ml_objective": task,
        },
    ).json()
    path = f"/api/v1/projects/{project['id']}/pipeline"
    before = client.get(path).json()
    invalid = deepcopy(before)
    invalid["ir"]["model"] = {"type": model}
    assert save(client, path, invalid).status_code == 422
    assert client.get(path).json() == before


@pytest.mark.parametrize("model", ["linear_regression", "ridge"])
def test_regression_feature_compatibility_uses_only_eligible_rows(client, model):
    _, _, path, state = setup(client, b"x,city,y\n1,a,2\n2,b,3\n,a,4\n4,a,5\n,,\n")
    state["ir"]["model"] = {"type": model}
    response = save(client, path, state).json()
    assert response["eligible_rows"] == 4 and not response["configuration_ready"]
    assert {i["code"] for i in response["issues"]} >= {"feature_missing_values", "feature_encoding"}
    assert (
        next(i for i in response["issues"] if i["code"] == "feature_missing_values")["field"]
        == "features.x.operations"
    )
    response["ir"]["features"]["x"]["operations"] = [{"type": "impute", "strategy": "median"}]
    response["ir"]["features"]["city"]["operations"] = [{"type": "encode", "method": "one_hot"}]
    response = save(client, path, response).json()
    assert response["configuration_ready"]
    # The only missing city is on an excluded target row, so city needs no imputer.
    assert response["ir"]["features"]["city"]["operations"] == [
        {"type": "encode", "method": "one_hot"}
    ]


def test_all_missing_regression_feature_and_dormant_operations(client):
    project, _, path, state = setup(client, b"x,z,y\n,1,2\n,2,3\n,3,4\n,4,5\n")
    assert configure(client, project, semantic_overrides={"x": "continuous"}).status_code == 200
    state = client.get(path).json()
    state["ir"]["model"] = {"type": "ridge"}
    state["ir"]["split"] = {}
    state["ir"]["features"]["x"]["operations"] = [{"type": "impute", "strategy": "mean"}]
    state = save(client, path, state).json()
    assert not state["configuration_ready"]
    assert any(i["code"] == "feature_all_missing" for i in state["issues"])
    state["ir"]["features"]["x"].update(
        included=False, operations=[{"type": "encode", "method": "one_hot"}]
    )
    state = save(client, path, state).json()
    assert state["configuration_ready"]
    assert any(
        i["code"] == "operation_incompatible" and i["severity"] == "non_blocking"
        for i in state["issues"]
    )
