"""Catalogue facts come from the same typed models and contextual rules as editing."""

import json

import pytest
from test_train_configuration import DEFAULTS, intent

from mlstudio.codegen.plan import classifier
from mlstudio.model_catalog import model_catalogue, model_defaults
from mlstudio.pipeline_schemas import RegressionPipelineIR


@pytest.mark.parametrize(
    "task,expected",
    [
        ("binary_classification", DEFAULTS),
        (
            "regression",
            {
                "linear_regression": {"fit_intercept": True},
                "ridge": {"alpha": 1.0, "fit_intercept": True},
            },
        ),
    ],
)
def test_catalogue_complete_deterministic_and_schema_consistent(task, expected):
    descriptors = model_catalogue(task)
    assert [item.id for item in descriptors] == list(expected)
    defaults = model_defaults(task)
    assert {item.type: item.parameters.model_dump() for item in defaults} == expected
    for item, model in zip(descriptors, defaults, strict=True):
        assert item.catalogue_version == "model-catalog-v1" and item.task == task
        assert item.name and item.compiler_adapter
        assert item.defaults == expected[item.id]
        assert item.parameter_schema == type(model.parameters).model_json_schema()
        assert set(item.parameter_schema["properties"]) == set(item.defaults)
        assert item.feature_requirements.requires_numeric_input
        assert item.feature_requirements.requires_complete_features
        assert item.feature_requirements.supports_sparse
        assert item.feature_requirements.supported_semantics == [
            "continuous",
            "categorical",
            "binary",
        ]
        if task == "regression":
            restored = RegressionPipelineIR.model_validate(
                {
                    "ir_version": "0.2",
                    "task": task,
                    "model": {"type": item.id, "parameters": item.defaults},
                }
            )
            assert restored.model == model
    payload = [item.model_dump(mode="json") for item in descriptors]
    encoded = json.dumps(payload, allow_nan=False)
    assert encoded == json.dumps([d.model_dump(mode="json") for d in model_catalogue(task)])
    assert "sklearn.linear_model" not in encoded and "import_path" not in encoded


@pytest.mark.parametrize(
    "model,adapter,constructor",
    [
        ("logistic_regression", "sklearn-logistic-v1", "LogisticRegression"),
        ("decision_tree", "sklearn-tree-classifier-v1", "DecisionTreeClassifier"),
        ("random_forest", "sklearn-forest-classifier-v1", "RandomForestClassifier"),
    ],
)
def test_binary_descriptor_defaults_keep_existing_compiler_behavior(model, adapter, constructor):
    descriptor = next(d for d in model_catalogue("binary_classification") if d.id == model)
    assert descriptor.defaults == DEFAULTS[model]
    assert descriptor.compiler_adapter == adapter
    assert classifier(intent(model)).name == constructor


def test_catalogue_exposes_contextual_constraints_without_changing_legacy_syntax():
    logistic, tree, forest = model_catalogue("binary_classification")
    assert logistic.contextual_constraints["C"].exclusive_minimum == 0
    assert logistic.contextual_constraints["penalty"].choices == ["l1", "l2"]
    assert tree.contextual_constraints["max_depth"].allow_none
    assert tree.contextual_constraints["min_samples_split"].minimum == 2
    assert forest.contextual_constraints["n_estimators"].minimum == 1
    # Legacy editing permits these finite invalid ranges for contextual correction.
    assert intent(parameters={"C": -1}).model.parameters.C == -1
    ridge = model_catalogue("regression")[1]
    assert ridge.parameter_schema["properties"]["alpha"]["minimum"] == 0


def test_catalogue_returns_detached_metadata_and_rejects_unknown_tasks():
    model_catalogue("regression")[0].defaults["fit_intercept"] = False
    assert model_catalogue("regression")[0].defaults["fit_intercept"] is True
    with pytest.raises(ValueError):
        model_catalogue("clustering")
