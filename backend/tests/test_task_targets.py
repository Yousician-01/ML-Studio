"""Explicit task contracts and numeric target intent; no regression execution."""

from copy import deepcopy
from uuid import uuid4

import pandas as pd
import pytest
from pydantic import ValidationError
from test_projects_datasets import configure, create, upload

from mlstudio.models import Project
from mlstudio.pipeline_schemas import PipelineIR, load_ir
from mlstudio.services.source import DomainError
from mlstudio.services.task_policies import validate_target_for_task


def regression(client):
    response = client.post(
        "/api/v1/projects",
        json={"name": "Prices", "problem_statement": "Predict price", "ml_objective": "regression"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("objective", [None, "binary_classification", "regression"])
def test_project_task_creation_and_immutability(client, objective):
    body = {"name": "Task", "problem_statement": "Predict"}
    if objective is not None:
        body["ml_objective"] = objective
    response = client.post("/api/v1/projects", json=body)
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["ml_objective"] == (objective or "binary_classification")
    path = f"/api/v1/projects/{project['id']}"
    assert client.patch(path, json={"ml_objective": "regression"}).status_code == 422
    assert client.get(path).json() == project
    assert client.get("/api/v1/projects").json() == [project]


def test_unknown_project_task_rejected(client):
    assert (
        client.post(
            "/api/v1/projects",
            json={"name": "Task", "problem_statement": "Predict", "ml_objective": "clustering"},
        ).status_code
        == 422
    )


def test_orm_project_task_is_immutable_and_default_intent_matches_task(client):
    with client.app.state.session_factory() as session:
        project = Project(name="Numeric", problem_statement="Predict", ml_objective="regression")
        session.add(project)
        session.commit()
        assert project.working_pipeline["ir_version"] == "0.2"
        project.ml_objective = "binary_classification"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()
        assert project.ml_objective == "regression"


@pytest.mark.parametrize(
    "values,dtype",
    [([1.2, 2.7, None], None), ([7, 7, 7], None), ([0, 1, 0], None), ([1, None, 3], "Int64")],
)
def test_numeric_regression_targets_accept_missing_constant_and_two_values(values, dtype):
    frame = pd.DataFrame({"y": pd.Series(values, dtype=dtype)})
    validate_target_for_task(frame, "y", "regression")
    assert frame["y"].isna().sum() == sum(value is None for value in values)


@pytest.mark.parametrize(
    "series",
    [
        pd.Series([True, False]),
        pd.Series([True, None], dtype="boolean"),
        pd.Series(["yes", "no"]),
        pd.Series([1, 2], dtype=object),
        pd.Series([1.0, float("inf")]),
        pd.Series([float("-inf"), 3.0]),
        pd.Series([None, None], dtype="Float64"),
        pd.Series([2**53 + 1, 2**53 + 3], dtype="int64"),
        pd.Series([2**53 + 1, None], dtype="Int64"),
        pd.Series([2**64 - 1, 3], dtype="uint64"),
        pd.Series([1 + 2j, 3 + 4j]),
    ],
)
def test_unsafe_regression_target_rejected_without_coercion(series):
    frame = pd.DataFrame({"y": series})
    before = frame.copy(deep=True)
    with pytest.raises(DomainError):
        validate_target_for_task(frame, "y", "regression")
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("labels", ["2.5\n2.5\n2.5", "0\n1\n0", "1.5\n\n3.2"])
def test_regression_target_api_and_prepare_roundtrip(client, labels):
    project = regression(client)
    data = ("x,y\n" + "\n".join(f"{i},{v}" for i, v in enumerate(labels.split("\n")))).encode()
    assert upload(client, project, data).status_code == 201
    result = configure(client, project, target_column="y")
    assert result.status_code == 200, result.text
    assert result.json()["target_classes"] == []
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    assert state["target_missing_count"] == labels.split("\n").count("")
    assert state["eligible_rows"] == sum(bool(value) for value in labels.split("\n"))
    assert state["ir"]["ir_version"] == "0.2" and state["ir"]["task"] == "regression"
    assert state["ir"]["target"] == {
        "column": "y",
        "value_type": "numeric",
        "missing_value_policy": "exclude_rows",
    }
    assert state["target_classes"] == []
    assert [model["type"] for model in state["model_defaults"]] == ["linear_regression", "ridge"]
    assert state["prepare_valid"] and not state["code_generation_ready"]
    assert "stratify" not in state["split_defaults"]
    state["ir"]["features"]["x"]["operations"] = [{"type": "scale", "method": "standard"}]
    response = client.patch(path, json={"revision": state["revision"], "ir": state["ir"]})
    assert response.status_code == 200, response.text
    assert response.json()["ir"] == state["ir"]
    code = client.get(f"/api/v1/projects/{project['id']}/code").json()
    assert not code["ready"] and code["source"] is None
    assert any(issue["code"] == "model_missing" for issue in code["issues"])
    run = client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={
            "request_id": str(uuid4()),
            "expected_revision": response.json()["revision"],
            "expected_source_sha256": "sha256:" + "0" * 64,
            "expected_plan_sha256": "sha256:" + "0" * 64,
        },
    )
    assert run.status_code == 422 and "Pipeline is not ready" in run.json()["detail"]


@pytest.mark.parametrize("values", ["true\nfalse\ntrue", "yes\nno\nyes", "9007199254740993\n2\n3"])
def test_invalid_target_api_preserves_configuration(client, values):
    project = regression(client)
    data = ("x,y\n" + "\n".join(f"{i},{v}" for i, v in enumerate(values.split("\n")))).encode()
    assert upload(client, project, data).status_code == 201
    path = f"/api/v1/projects/{project['id']}"
    before = client.get(path).json()
    assert configure(client, project, target_column="y").status_code == 422
    assert client.get(path).json() == before


def test_replacement_retains_task_and_stale_intent_with_revision_guard(client):
    project = regression(client)
    first = upload(client, project, b"x,y\n1,10\n2,20\n3,30").json()
    assert configure(client, project, target_column="y").status_code == 200
    path = f"/api/v1/projects/{project['id']}/pipeline"
    original = client.get(path).json()
    second = upload(client, project, b"x,z\n1,5\n2,5\n3,5", expected=first["id"]).json()
    stale = client.get(path).json()
    assert stale["stale"] and stale["ir"] == original["ir"]
    assert (
        client.patch(
            path, json={"revision": original["revision"], "ir": original["ir"]}
        ).status_code
        == 409
    )
    assert configure(client, project, target_column="z").status_code == 200
    assert client.get(path).json()["ir"] == original["ir"]
    assert client.get(f"/api/v1/projects/{project['id']}").json()["ml_objective"] == "regression"
    state = client.get(path).json()
    reset = client.post(
        path + "/reset", json={"revision": state["revision"], "dataset_id": second["id"]}
    )
    assert reset.status_code == 200, reset.text
    assert not reset.json()["stale"] and reset.json()["ir"]["target"]["column"] == "z"
    assert reset.json()["ir"]["ir_version"] == "0.2"


def test_strict_ir_version_and_task_dispatch(client):
    project = regression(client)
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    assert load_ir(state["ir"], "regression").model_dump(mode="json") == state["ir"]
    for changes in [
        {"ir_version": "99"},
        {"task": "binary_classification"},
        {"target": {"column": "y", "positive_class": None}},
        {"target": {"column": "y", "missing_value_policy": "impute"}},
        {"split": {"stratify": False}},
        {"model": {"type": "logistic_regression"}},
    ]:
        ir = {**deepcopy(state["ir"]), **changes}
        assert client.patch(path, json={"revision": state["revision"], "ir": ir}).status_code == 422
    binary = PipelineIR().model_dump(mode="json")
    assert load_ir(binary, "binary_classification").model_dump(mode="json") == binary
    with pytest.raises((ValueError, ValidationError)):
        load_ir(binary, "regression")
    assert client.patch(path, json={"revision": state["revision"], "ir": binary}).status_code == 422


def test_legacy_binary_request_can_still_omit_ir_version(client):
    project = create(client)
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"].pop("ir_version")
    assert load_ir(state["ir"], "binary_classification").ir_version == "0.1"
    assert (
        client.patch(path, json={"revision": state["revision"], "ir": state["ir"]}).status_code
        == 200
    )


def test_regression_explore_has_explicit_task_and_no_target_state(client):
    project = regression(client)
    dataset = upload(client, project, b"x,y\n1,5\n2,6\n3,7").json()
    response = client.get(
        f"/api/v1/projects/{project['id']}/dataset/profile",
        params={"dataset_id": dataset["id"], "revision": dataset["revision"]},
    )
    assert response.status_code == 200
    assert response.json()["task"] == "regression" and response.json()["target"] is None
