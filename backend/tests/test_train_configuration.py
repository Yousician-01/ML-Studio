import copy

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_projects_datasets import configure, create, upload

from mlstudio.main import create_app
from mlstudio.pipeline_schemas import PipelineIR, SplitIntent
from mlstudio.services.train_validation import (
    partition_sizes,
    stratified_train_counts,
    train_issues,
)

DEFAULTS = {
    "logistic_regression": {"C": 1.0, "penalty": "l2", "max_iter": 1000},
    "decision_tree": {"max_depth": None, "min_samples_split": 2, "min_samples_leaf": 1},
    "random_forest": {
        "n_estimators": 100,
        "max_depth": None,
        "min_samples_split": 2,
        "min_samples_leaf": 1,
    },
}


def intent(model="logistic_regression", parameters=None, split=None):
    return PipelineIR.model_validate(
        {
            "model": {"type": model, "parameters": parameters or {}},
            "split": {} if split is None else split,
        }
    )


@pytest.mark.parametrize("model", DEFAULTS)
def test_explicit_defaults(model):
    ir = intent(model)
    assert ir.model.parameters.model_dump() == DEFAULTS[model]
    assert ir.split.model_dump() == {"test_size": 0.2, "random_seed": 42, "stratify": True}
    assert not train_issues(ir, pd.Series(["a", "b"] * 20))


@pytest.mark.parametrize(
    "model,parameter,value,valid",
    [
        ("logistic_regression", "C", 1e-12, True),
        ("logistic_regression", "C", 1e7, True),
        ("logistic_regression", "C", 0, False),
        ("logistic_regression", "C", -1, False),
        ("logistic_regression", "C", None, False),
        ("logistic_regression", "penalty", "l1", True),
        ("logistic_regression", "penalty", "l2", True),
        ("logistic_regression", "penalty", None, False),
        ("logistic_regression", "max_iter", 1, True),
        ("logistic_regression", "max_iter", 0, False),
        *[
            (m, p, v, ok)
            for m in ["decision_tree", "random_forest"]
            for p, v, ok in [
                ("max_depth", None, True),
                ("max_depth", 1, True),
                ("max_depth", 0, False),
                ("min_samples_split", 2, True),
                ("min_samples_split", 1, False),
                ("min_samples_leaf", 1, True),
                ("min_samples_leaf", 0, False),
                ("min_samples_leaf", None, False),
            ]
        ],
        ("random_forest", "n_estimators", 1, True),
        ("random_forest", "n_estimators", 0, False),
        ("random_forest", "n_estimators", None, False),
    ],
)
def test_model_ranges_are_saveable_contextual_issues(model, parameter, value, valid):
    ir = intent(model, {parameter: value})
    issues = train_issues(ir, None)
    assert (not issues) == valid
    assert ir.model.parameters.model_dump()[parameter] == value
    if not valid:
        assert issues[0].field == f"model.parameters.{parameter}"


@pytest.mark.parametrize(
    "model,parameter",
    [(m, p) for m in DEFAULTS for p in ["unexpected", "class_weight", "solver", "random_state"]]
    + [
        ("decision_tree", "criterion"),
        ("random_forest", "criterion"),
        ("random_forest", "max_features"),
    ],
)
def test_unsupported_parameters_rejected(model, parameter):
    with pytest.raises(ValidationError):
        intent(model, {parameter: None})


@pytest.mark.parametrize(
    "model,parameter,value",
    [
        ("logistic_regression", "C", True),
        ("logistic_regression", "C", float("inf")),
        ("logistic_regression", "C", "1"),
        ("logistic_regression", "max_iter", 1.5),
        ("logistic_regression", "penalty", "elasticnet"),
        ("decision_tree", "max_depth", True),
        ("random_forest", "n_estimators", False),
    ],
)
def test_parameter_types_are_strict(model, parameter, value):
    with pytest.raises(ValidationError):
        intent(model, {parameter: value})


@pytest.mark.parametrize(
    "field,value,valid",
    [
        ("test_size", 0.05, True),
        ("test_size", 0.2, True),
        ("test_size", 0.5, True),
        ("test_size", 0.049, False),
        ("test_size", 0.501, False),
        ("test_size", None, False),
        ("random_seed", 0, True),
        ("random_seed", 42, True),
        ("random_seed", 2147483647, True),
        ("random_seed", -1, False),
        ("random_seed", 2147483648, False),
        ("random_seed", None, False),
        ("stratify", True, True),
        ("stratify", False, True),
        ("stratify", None, False),
    ],
)
def test_split_boundaries(field, value, valid):
    assert (not train_issues(intent(split={field: value}), None)) == valid


@pytest.mark.parametrize(
    "field,value",
    [
        ("test_size", True),
        ("test_size", "0.2"),
        ("random_seed", True),
        ("random_seed", 1.2),
        ("stratify", 1),
        ("stratify", "true"),
    ],
)
def test_split_types(field, value):
    with pytest.raises(ValidationError):
        SplitIntent.model_validate({field: value})


@pytest.mark.parametrize(
    "counts,fraction,seed,expected",
    [
        ([10, 10], 0.2, 42, None),
        ([1, 19], 0.2, 42, "stratify_class_count"),
        ([2, 2], 0.05, 42, "stratify_partition"),
        ([2, 98], 0.2, 42, "stratify_allocation"),
        ([2, 6], 0.25, 0, None),
        ([2, 6], 0.25, 1, "stratify_allocation"),
        ([3, 3], 0.5, 42, None),
    ],
)
def test_stratification_integer_counts(counts, fraction, seed, expected):
    target = pd.Series(["a"] * counts[0] + ["b"] * counts[1] + [None] * 7)
    ir = intent(split={"test_size": fraction, "random_seed": seed})
    issues = train_issues(ir, target)
    assert [i.code for i in issues] == ([expected] if expected else [])
    # Non-stratified intent never samples to speculate about representation.
    ir.split.stratify = False
    assert not train_issues(ir, target)


def test_partition_rounding_and_small_training_population():
    assert partition_sizes(11, SplitIntent(test_size=0.2)) == (8, 3)
    assert stratified_train_counts([5, 2], 4, 0).tolist() == [3, 1]
    assert stratified_train_counts([4, 2], 3, 0).tolist() == [2, 1]
    assert "stratify_class_count" in [
        i.code for i in train_issues(intent(split={"test_size": 0.5}), pd.Series(["a", "b"]))
    ]


def experiment(client):
    project = create(client)
    rows = [f"{20 + i},{'yes' if i % 2 else 'no'},{'a' if i == 0 else 'b'},west" for i in range(20)]
    dataset = upload(client, project, ("age,label,other,city\n" + "\n".join(rows)).encode()).json()
    configure(client, project, target_column="label")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
    for name, feature in state["ir"]["features"].items():
        feature["included"] = name == "age"
    state["ir"]["model"] = {"type": "logistic_regression"}
    state["ir"]["split"] = {}
    return project, dataset, path, state


def save(client, path, state):
    return client.patch(path, json={"revision": state["revision"], "ir": state["ir"]})


def test_complete_persistence_switching_revision_and_reconciliation(client, settings):
    project, dataset, path, state = experiment(client)
    stale = copy.deepcopy(state)
    response = save(client, path, state)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["code_generation_ready"] and state["prepare_valid"]
    assert not state["executable"] and state["issues"] == []
    assert (state["eligible_rows"], state["train_rows"], state["test_rows"]) == (20, 16, 4)
    assert save(client, path, stale).status_code == 409
    state["ir"]["model"]["parameters"]["C"] = 2.5
    state = save(client, path, state).json()
    for model in ["random_forest", "decision_tree", "logistic_regression"]:
        state["ir"]["model"] = {"type": model}
        state = save(client, path, state).json()
        assert state["ir"]["model"]["parameters"] == DEFAULTS[model]
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path).json() == state
    configured = copy.deepcopy(state["ir"])
    configure(client, project, target_column="other")
    changed = client.get(path).json()
    assert changed["ir"]["model"] == configured["model"]
    assert changed["ir"]["split"] == configured["split"]
    assert changed["ir"]["target"]["positive_class"] is None
    assert changed["ir"]["features"]["label"]["included"] is False
    assert any(i["code"] == "stratify_class_count" for i in changed["issues"])
    assert not changed["code_generation_ready"]
    upload(client, project, expected=dataset["id"])
    replaced = client.get(path).json()
    assert replaced["stale"] and not replaced["code_generation_ready"]
    assert replaced["ir"] == changed["ir"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda ir: ir.update(model=None), "model_missing"),
        (lambda ir: ir.update(split=None), "split_missing"),
        (lambda ir: ir.update(target=None), "target_missing"),
        (lambda ir: ir["target"].update(positive_class=None), "positive_class_missing"),
        (lambda ir: ir["model"]["parameters"].update(C=0), "model_parameter"),
        (lambda ir: ir["split"].update(test_size=0.9), "test_size_invalid"),
        (lambda ir: ir["features"]["age"].update(included=False), "features_empty"),
        (
            lambda ir: ir["features"]["age"].update(
                operations=[{"type": "encode", "method": "one_hot"}]
            ),
            "operation_incompatible",
        ),
        (lambda ir: ir["features"]["city"].update(included=True), "feature_encoding"),
    ],
)
def test_incomplete_and_invalid_intent_persists(client, mutation, code):
    _, _, path, state = experiment(client)
    state = save(client, path, state).json()
    mutation(state["ir"])
    response = save(client, path, state)
    assert response.status_code == 200
    assert not response.json()["code_generation_ready"]
    assert code in {i["code"] for i in response.json()["issues"]}
    assert client.get(path).json()["ir"] == response.json()["ir"]


def test_semantics_and_dormant_operations(client):
    project, _, path, state = experiment(client)
    state["ir"]["features"]["age"]["operations"] = [{"type": "scale", "method": "standard"}]
    state = save(client, path, state).json()
    configure(client, project, semantic_overrides={"age": "categorical"})
    state = client.get(path).json()
    assert not state["code_generation_ready"]
    assert state["ir"]["features"]["age"]["operations"]
    state["ir"]["features"]["age"]["included"] = False
    state["ir"]["features"]["city"].update(
        included=True, operations=[{"type": "encode", "method": "one_hot"}]
    )
    state = save(client, path, state).json()
    assert state["code_generation_ready"]
    assert all(i["severity"] == "non_blocking" for i in state["issues"])


@pytest.mark.parametrize("model", DEFAULTS)
def test_missing_feature_compatibility_uses_eligible_targets(client, model):
    project = create(client)
    upload(client, project, b"x,y\n1,a\n2,b\n3,a\n4,b\n,a\n,b\n,\n")
    configure(client, project, target_column="y")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["model"] = {"type": model}
    state["ir"]["split"] = {"test_size": 0.5}
    state["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "a"}
    state = save(client, path, state).json()
    assert state["eligible_rows"] == 6 and state["target_missing_count"] == 1
    assert any(i["code"] == "feature_missing_values" for i in state["issues"])
    state["ir"]["features"]["x"]["operations"] = [{"type": "impute", "strategy": "median"}]
    state = save(client, path, state).json()
    assert state["code_generation_ready"]


def test_all_missing_feature_is_not_made_valid_by_imputation(client):
    project = create(client)
    upload(client, project, b"x,y\n,a\n,b\n,a\n,b\n,a\n,b\n")
    configure(client, project, target_column="y", semantic_overrides={"x": "continuous"})
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["model"] = {"type": "decision_tree"}
    state["ir"]["split"] = {"test_size": 0.5}
    state["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "a"}
    state["ir"]["features"]["x"]["operations"] = [{"type": "impute", "strategy": "median"}]
    state = save(client, path, state).json()
    assert not state["code_generation_ready"]
    assert any(i["code"] == "feature_all_missing" for i in state["issues"])
