"""Exploratory evidence remains separate from frozen training-only treatment."""

import numpy as np
import pandas as pd
import pytest


def recipe(**extra):
    return {
        "version": "outlier-treatment-v1",
        "features": [
            {
                "source": "x",
                "name": "capped",
                "multiplier": 1.5,
                "tails": "both",
                "indicator": "flag",
                "missing": "preserve",
                "invalid": "reject",
                **extra,
            }
        ],
    }


def test_existing_numeric_profile_iqr_variance_and_degenerate_evidence():
    from mlstudio.services.profiles import numeric_profile

    data = pd.Series([0.0, 1.0, 2.0, 3.0, 100.0, np.nan])
    stats = numeric_profile(data, 1.5)
    assert (stats.q1, stats.median, stats.q3, stats.iqr) == (1.0, 2.0, 3.0, 2.0)
    assert (stats.below_fence_count, stats.above_fence_count, stats.outlier_count) == (0, 1, 1)
    assert stats.outlier_percentage == 20 and stats.variance == pytest.approx(np.var(data.dropna()))
    assert numeric_profile(data, 10).upper_fence == 23
    assert numeric_profile(pd.Series([2.0, 2.0])).iqr == 0
    assert numeric_profile(pd.Series([np.nan])).outlier_percentage is None
    assert numeric_profile(pd.Series([np.inf, 1.0])).unavailable_reason


def test_iqr_fit_training_only_shared_indicator_and_tail_policies():
    from mlstudio.outlier_runtime_v1 import OutlierFeatures

    train = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0, 4.0, np.nan]})
    fitted = OutlierFeatures(recipe()).fit(train)
    assert fitted.fences_["capped"] == (-2.0, 6.0)
    test = pd.DataFrame({"x": [-100.0, 100.0, np.nan]})
    result = fitted.transform(test)
    assert result.capped.iloc[:2].tolist() == [-2.0, 6.0]
    assert result.flag.iloc[:2].tolist() == [1.0, 1.0]
    assert result.loc[2, ["capped", "flag"]].isna().all()
    assert fitted.fences_["capped"] == (-2.0, 6.0)
    lower = OutlierFeatures(recipe(tails="lower")).fit(train).transform(test)
    assert lower.capped.iloc[:2].tolist() == [-2.0, 100.0]
    assert lower.flag.iloc[:2].tolist() == [1.0, 0.0]


def test_outlier_degenerate_missing_nonfinite_and_zero_iqr():
    from mlstudio.outlier_runtime_v1 import OutlierFeatures

    for values in [[np.nan, np.nan], [1.0], [np.inf, 2.0]]:
        with pytest.raises(ValueError):
            OutlierFeatures(recipe()).fit(pd.DataFrame({"x": values}))
    constant = OutlierFeatures(recipe()).fit(pd.DataFrame({"x": [2.0, 2.0, 2.0]}))
    assert constant.transform(pd.DataFrame({"x": [2.0, 9.0]})).capped.tolist() == [2.0, 2.0]
    assert constant.diagnostics_["capped"] == "zero_iqr"
    with pytest.raises(ValueError, match="missing"):
        OutlierFeatures(recipe(missing="reject")).fit(pd.DataFrame({"x": [1.0, 2.0, np.nan]}))
    result = (
        OutlierFeatures(recipe(invalid="coerce"))
        .fit(pd.DataFrame({"x": [1.0, 2.0]}))
        .transform(pd.DataFrame({"x": [np.inf]}))
    )
    assert result.capped.isna().all() and result.flag.isna().all()


def test_variance_uses_fitted_branch_slices_preserves_categorical_order():
    from scipy import sparse
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    from mlstudio.outlier_runtime_v1 import SelectedPreprocessor

    frame = pd.DataFrame(
        {"x": [1.0, 2.0, 3.0], "constant": [7.0, 7.0, 7.0], "category": ["a", "b", "a"]}
    )
    preprocessor = ColumnTransformer(
        [
            ("x", StandardScaler(), ["x"]),
            ("constant", "passthrough", ["constant"]),
            ("category", OneHotEncoder(handle_unknown="ignore"), ["category"]),
        ],
        sparse_threshold=1.0,
    )
    selector = SelectedPreprocessor(
        preprocessor, {"threshold": 0.01, "branches": {"x": "x", "constant": "constant"}}
    )
    result = selector.fit_transform(frame)
    assert sparse.issparse(result) and result.shape == (3, 3)
    assert selector.selected_features_ == ["x"] and selector.mask_.tolist() == [
        True,
        False,
        True,
        True,
    ]
    before = selector.mask_.copy()
    assert selector.transform(
        pd.DataFrame({"x": [100.0], "constant": [100.0], "category": ["new"]})
    ).shape == (1, 3)
    np.testing.assert_array_equal(before, selector.mask_)


def test_variance_rejects_no_eligible_survivors_and_unhandled_missing():
    from sklearn.compose import ColumnTransformer

    from mlstudio.outlier_runtime_v1 import SelectedPreprocessor

    for values, match in [([1.0, 1.0], "No eligible"), ([1.0, np.nan], "missing")]:
        with pytest.raises(ValueError, match=match):
            SelectedPreprocessor(
                ColumnTransformer([("x", "passthrough", ["x"])]),
                {"threshold": 0.0, "branches": {"x": "x"}},
            ).fit_transform(pd.DataFrame({"x": values}))


def test_schema_preview_and_persistence_never_fit(client, monkeypatch):
    from test_projects_datasets import configure, create, upload

    from mlstudio.outlier_runtime_v1 import OutlierFeatures
    from mlstudio.outlier_schemas import OutlierConfig

    for bad in [recipe(multiplier=0), recipe(multiplier=100), recipe(indicator="capped")]:
        with pytest.raises(ValueError):
            OutlierConfig.model_validate(bad)
    monkeypatch.setattr(OutlierFeatures, "fit", lambda *args: pytest.fail("preview fitted source"))
    project = create(client)
    upload(client, project, b"x,label\n1,yes\n2,no\n4,yes\n100,no\n")
    configure(client, project, target_column="label")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    ir = state["ir"]
    ir["outlier_treatment"] = recipe()
    ir["features"].update(
        {name: {"included": True, "operations": []} for name in ["capped", "flag"]}
    )
    ir["feature_selection"] = {
        "version": "feature-selection-v1",
        "method": "variance_threshold",
        "stage": "post_preprocessing",
        "features": ["capped"],
        "threshold": 0.0,
    }
    body = {"revision": state["revision"], "ir": ir}
    response = client.post(path + "/temporal-preview", json=body)
    assert response.status_code == 200, response.text
    assert not response.json()["errors"]
    assert response.json()["outlier_treatment"]["capped"]["fitted"]
    assert "capped" not in [c["name"] for c in response.json()["columns"]]
    assert response.json()["feature_selection"]["stage"] == "post_preprocessing"
    saved = client.patch(path, json=body)
    assert saved.status_code == 200, saved.text
    assert (
        client.get(path).json()["ir"]["outlier_treatment"]
        == saved.json()["ir"]["outlier_treatment"]
    )
    assert (
        client.get(path).json()["ir"]["feature_selection"]
        == saved.json()["ir"]["feature_selection"]
    )
    invalid = saved.json()["ir"]
    invalid["outlier_treatment"]["features"][0]["source"] = "label"
    invalid_result = client.post(
        path + "/temporal-preview", json={"revision": saved.json()["revision"], "ir": invalid}
    )
    assert invalid_result.json()["errors"]


def test_three_task_generated_execution_and_fresh_process_inference(tmp_path, monkeypatch):
    from test_feature_engineering import (
        test_compiler_all_tasks_extensions_and_fresh_process_inference,
    )

    import mlstudio.pipeline_schemas as schemas

    original = schemas.load_ir

    def load(payload, task):
        payload["outlier_treatment"] = recipe(source="q")
        payload["features"].update(
            {
                "capped": {
                    "included": True,
                    "operations": [{"type": "impute", "strategy": "median"}],
                },
                "flag": {
                    "included": True,
                    "operations": [{"type": "impute", "strategy": "most_frequent"}],
                },
            }
        )
        payload["feature_selection"] = {
            "version": "feature-selection-v1",
            "method": "variance_threshold",
            "stage": "post_preprocessing",
            "features": ["logged", "month_log", "capped"],
            "threshold": 0.0,
        }
        return original(payload, task)

    monkeypatch.setattr(schemas, "load_ir", load)
    test_compiler_all_tasks_extensions_and_fresh_process_inference(tmp_path)
