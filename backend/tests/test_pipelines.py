import copy
from pathlib import Path

import pandas as pd
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm.exc import StaleDataError
from test_projects_datasets import configure, create, upload

from alembic import command
from mlstudio.main import create_app
from mlstudio.models import Dataset, Project
from mlstudio.pipeline_schemas import PipelineIR
from mlstudio.services.pipelines import validate


def setup(client):
    project = create(client)
    dataset = upload(client, project).json()
    configure(client, project, target_column="churn")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    return project, dataset, path, client.get(path).json()


def save(client, path, state):
    return client.patch(path, json={"revision": state["revision"], "ir": state["ir"]})


def codes(state):
    return {i["code"] for i in state["issues"]}


def test_initialization_read_only_and_restart(client, settings):
    project = create(client)
    path = f"/api/v1/projects/{project['id']}/pipeline"
    initial = client.get(path).json()
    assert initial["ir"] == {
        "ir_version": "0.1",
        "dataset": None,
        "target": None,
        "features": {},
        "model": None,
        "split": None,
    }
    assert client.get(f"/api/v1/projects/{project['id']}").json() == project
    dataset = upload(client, project).json()
    current = client.get(path).json()
    assert current["ir"]["dataset"] == {
        "dataset_id": dataset["id"],
        "fingerprint": dataset["fingerprint"],
    }
    assert all(
        f == {"included": True, "operations": []} for f in current["ir"]["features"].values()
    )
    assert "target_missing" in codes(current)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path).json() == current


@pytest.mark.parametrize(
    "labels,expected",
    [
        ("yes\nno\nyes", {"value_type": "string", "value": "yes"}),
        ("0\n1\n0", {"value_type": "integer", "value": 0}),
        (
            "9007199254740992\n9007199254740993\n",
            {"value_type": "integer", "value": "9007199254740992"},
        ),
        (
            "-9007199254740993\n-9007199254740992\n",
            {"value_type": "integer", "value": "-9007199254740993"},
        ),
        ("1.0\n2.0\n1.0", {"value_type": "float", "value": 1.0}),
        ("true\nfalse\ntrue", {"value_type": "boolean", "value": True}),
    ],
)
def test_typed_positive_class_roundtrip(client, settings, labels, expected):
    project = create(client)
    rows = labels.split("\n")
    content = ("x,y\n" + "\n".join(f"{i},{v}" for i, v in enumerate(rows))).encode()
    upload(client, project, content)
    configure(client, project, target_column="y")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    assert state["target_classes"][0] == expected
    state["ir"]["target"]["positive_class"] = expected
    # Simulate JS JSON.stringify(1.0) -> 1 while retaining the float tag.
    if expected["value_type"] == "float":
        state["ir"]["target"]["positive_class"]["value"] = 1
    response = save(client, path, state)
    assert response.status_code == 200, response.text
    result = response.json()
    assert "positive_class_invalid" not in codes(result)
    assert result["ir"]["target"]["missing_value_policy"] == "exclude_rows"
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path).json()["ir"] == result["ir"]


def test_editable_invalid_intent_and_dormant_validation(client):
    project, _, path, state = setup(client)
    state["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "not-a-class"}
    state["ir"]["features"]["amount"]["operations"] = [
        {"type": "scale", "method": "standard"},
        {"type": "impute", "strategy": "median"},
        {"type": "scale", "method": "robust"},
        {"type": "encode", "method": "one_hot"},
    ]
    result = save(client, path, state)
    assert result.status_code == 200
    state = result.json()
    assert {
        "positive_class_invalid",
        "operation_order",
        "duplicate_operation",
        "operation_combination",
        "operation_incompatible",
        "unsupported_semantic",
    } <= codes(state)
    ops = copy.deepcopy(state["ir"]["features"]["amount"]["operations"])
    state["ir"]["features"]["amount"]["included"] = False
    state = save(client, path, state).json()
    assert state["ir"]["features"]["amount"]["operations"] == ops
    assert all(i["severity"] == "non_blocking" for i in state["issues"] if i["column"] == "amount")
    configure(client, project, semantic_overrides={"amount": "categorical"})
    state = client.get(path).json()
    assert all(i["severity"] == "non_blocking" for i in state["issues"] if i["column"] == "amount")
    state["ir"]["features"]["amount"]["included"] = True
    assert any(
        i["severity"] == "blocking"
        for i in save(client, path, state).json()["issues"]
        if i["column"] == "amount"
    )


def test_valid_prepare_and_role_views(client):
    project, _, path, state = setup(client)
    state["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
    state["ir"]["features"]["customer_id"]["included"] = False
    state["ir"]["features"]["amount"]["operations"] = [
        {"type": "impute", "strategy": "median"},
        {"type": "scale", "method": "robust"},
    ]
    state["ir"]["features"]["segment"]["operations"] = [
        {"type": "impute", "strategy": "most_frequent"},
        {"type": "encode", "method": "one_hot"},
    ]
    state = save(client, path, state).json()
    assert state["prepare_valid"] and not state["executable"]
    assert codes(state) == {"model_missing", "split_missing"}
    source = client.get(path.removesuffix("pipeline") + "dataset").json()
    assert source["columns"][0]["role"] == "excluded"
    profile = client.get(
        path.removesuffix("pipeline")
        + f"dataset/profile?dataset_id={source['id']}&revision={state['revision']}"
    ).json()
    assert profile["columns"][0]["role"] == "excluded"
    assert profile["feature_count"] == 3


def test_replacement_target_change_and_concurrency(client, settings):
    project, dataset, path, state = setup(client)
    state["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
    state["ir"]["features"]["amount"]["operations"] = [{"type": "scale", "method": "min_max"}]
    stale = copy.deepcopy(state)
    state = save(client, path, state).json()
    assert save(client, path, stale).status_code == 409
    configure(client, project, target_column="alternate")
    changed = client.get(path).json()
    assert changed["ir"]["target"] == {
        "column": "alternate",
        "positive_class": None,
        "missing_value_policy": "exclude_rows",
    }
    assert changed["ir"]["features"]["churn"] == {"included": False, "operations": []}
    assert "alternate" not in changed["ir"]["features"]
    assert changed["ir"]["features"]["amount"] == state["ir"]["features"]["amount"]
    changed["ir"]["features"]["churn"]["included"] = True
    changed = save(client, path, changed).json()
    assert (
        client.get(path.removesuffix("pipeline") + "dataset").json()["columns"][3]["role"]
        == "feature"
    )
    replacement = upload(client, project, expected=dataset["id"]).json()
    result = client.get(path).json()
    assert result["stale"] and result["ir"] == changed["ir"]
    configure(client, project, target_column="churn")
    result = client.get(path).json()
    assert result["ir"] == changed["ir"]
    assert (
        client.post(
            path + "/reset", json={"revision": changed["revision"], "dataset_id": replacement["id"]}
        ).status_code
        == 409
    )
    result = client.post(
        path + "/reset", json={"revision": result["revision"], "dataset_id": replacement["id"]}
    ).json()
    assert not result["stale"] and result["ir"]["dataset"]["dataset_id"] == replacement["id"]
    assert result["ir"]["target"]["column"] == "churn"
    with client.app.state.session_factory() as session:
        old = session.get(Dataset, dataset["id"])
        assert (settings.home / old.source_relative_path).exists()
    with client.app.state.session_factory() as first, client.app.state.session_factory() as second:
        a, b = first.get(Project, project["id"]), second.get(Project, project["id"])
        a.working_pipeline = {**a.working_pipeline, "features": {}}
        first.commit()
        b.working_pipeline = {**b.working_pipeline, "target": None}
        with pytest.raises(StaleDataError):
            second.commit()


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda ir: ir["features"].pop("amount"), "feature_missing"),
        (
            lambda ir: ir["features"].update(ghost={"included": False, "operations": []}),
            "feature_absent",
        ),
        (
            lambda ir: ir["features"].update(churn={"included": False, "operations": []}),
            "target_feature",
        ),
        (lambda ir: [f.update(included=False) for f in ir["features"].values()], "features_empty"),
        (lambda ir: ir.update(target=None), "target_missing"),
        (lambda ir: ir["target"].update(column="absent"), "target_missing_column"),
        (lambda ir: ir["target"].update(column="segment"), "target_not_binary"),
    ],
)
def test_invalid_states_persist(client, mutation, code):
    _, _, path, state = setup(client)
    mutation(state["ir"])
    result = save(client, path, state)
    assert result.status_code == 200
    assert code in codes(result.json())
    assert client.get(path).json()["ir"] == result.json()["ir"]


@pytest.mark.parametrize(
    "field,value", [("ir_version", "9"), ("model", {"type": "logistic_regression"}), ("split", {})]
)
def test_structural_boundary(client, field, value):
    _, _, path, state = setup(client)
    state["ir"][field] = value
    assert save(client, path, state).status_code == 422


def test_fixed_policy_and_scalar_type_validation(client):
    _, _, path, state = setup(client)
    state["ir"]["target"]["missing_value_policy"] = "impute"
    assert save(client, path, state).status_code == 422
    state["ir"]["target"]["missing_value_policy"] = "exclude_rows"
    state["ir"]["target"]["positive_class"] = {"value_type": "integer", "value": True}
    assert save(client, path, state).status_code == 422


def test_validator_physical_semantics_and_binary_values():
    frame = pd.DataFrame({"number": ["a", "b"], "y": [1, 2]})
    dataset = Dataset(
        id="d",
        fingerprint="f",
        columns=[
            {
                "name": "number",
                "semantic_override": "continuous",
                "inferred_semantic_type": "binary",
            },
            {"name": "y", "semantic_override": None, "inferred_semantic_type": "binary"},
        ],
    )
    ir = PipelineIR.model_validate(
        {
            "dataset": {"dataset_id": "d", "fingerprint": "f"},
            "target": {"column": "y", "positive_class": {"value_type": "boolean", "value": True}},
            "features": {"number": {"included": True, "operations": []}},
        }
    )
    issues, _, _, _ = validate(ir, dataset, "y", frame)
    assert {"physical_mismatch", "positive_class_invalid"} <= {i.code for i in issues}


def test_phase_two_upgrade_preserves_roles(settings):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    command.upgrade(config, "0002_project_dataset")
    engine = create_engine(settings.resolved_database_url)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO projects (id,name,problem_statement,ml_objective,"
                "created_at,updated_at,"
                "former_targets,revision) VALUES ('p','P','Predict',"
                "'binary_classification','now','now','[\"a\"]',4)"
            )
        )
        c.execute(
            text(
                "INSERT INTO datasets (id,project_id,original_filename,"
                "format,created_at,fingerprint,"
                "source_relative_path,size_bytes,row_count,column_count,missing_cells,"
                "duplicate_rows,parsing_version,pandas_version,columns) VALUES "
                "('d','p','a.csv','csv','now','hash','path',1,2,3,0,0,'v','v',"
                '\'[{"name":"a"},{"name":"b"},{"name":"c"}]\')'
            )
        )
        c.execute(text("UPDATE projects SET active_dataset_id='d',target_column='b'"))
    engine.dispose()
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app(settings)) as app:
        with app.app.state.session_factory() as session:
            project = session.get(Project, "p")
            assert project.revision == 4 and project.updated_at == "now"
            assert project.working_pipeline["features"] == {
                "a": {"included": False, "operations": []},
                "c": {"included": True, "operations": []},
            }
