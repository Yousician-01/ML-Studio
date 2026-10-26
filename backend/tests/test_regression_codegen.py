"""Real standalone v2 programs and stable v1/v2 compiler dispatch."""

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pytest
from regression_fixtures import plan_for, prepared
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from test_codegen import FIXED_LIBRARIES, GOLDENS, golden_plan

REGRESSION_HASHES = {
    "linear": "a477f1c2ef820501945a78fa7ee9a6f13f1eff07625d853f0cbf2f6fd51d054f",
    "ridge_sparse": "17b8f93a938ef6d12f94e47f6076748a7eae081704f080ce1c5dd348f70bfb4a",
}


def regression_golden_plan(case):
    from mlstudio.codegen.dispatch import load_plan

    plan, _, _ = plan_for(
        "ridge" if case == "ridge_sparse" else "linear_regression", mixed=case == "ridge_sparse"
    )
    payload = plan.model_dump(mode="json")
    payload["implementation"].update(libraries=FIXED_LIBRARIES, python="3.14.2")
    return load_plan(payload)


@pytest.mark.parametrize(
    "matrix",
    [
        np.array([[0.0, 1.0], [1.0, 0.0], [2.0, 1.0], [3.0, 0.0]]),
        sparse.csr_matrix([[0.0, 1.0], [1.0, 0.0], [2.0, 1.0], [3.0, 0.0]]),
    ],
)
def test_pinned_ridge_lsqr_dense_and_sparse_before_golden(matrix):
    model = Ridge(
        alpha=1.0,
        fit_intercept=True,
        solver="lsqr",
        tol=1e-6,
        max_iter=10000,
        copy_X=True,
        positive=False,
        random_state=None,
    )
    model.fit(matrix, np.array([1.0, 3.0, 5.0, 7.0]))
    # Centered normal equations: [[6,-1],[-1,2]] beta = [10,-2].
    # Thus beta=[18/11,-2/11], intercept=18/11, independently of LSQR.
    np.testing.assert_allclose(model.predict(matrix), np.array([16, 36, 52, 72]) / 11, rtol=1e-6)
    assert np.isfinite(model.coef_).all() and max(model.n_iter_) <= 10000


def execute(tmp_path, plan, data):
    from mlstudio.codegen.dispatch import generate_for_version
    from mlstudio.execution.result_dispatch import validate_result_for_version

    source = generate_for_version(plan).encode()
    path = tmp_path / "generated_run.py"
    path.write_bytes(source)
    source_hash = "sha256:" + hashlib.sha256(source).hexdigest()
    dataset = tmp_path / "source.csv"
    dataset.write_bytes(data)
    result, model = tmp_path / "result.json", tmp_path / "model.joblib"
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            "-X",
            "utf8",
            str(path),
            "--dataset",
            str(dataset),
            "--result",
            str(result),
            "--model",
            str(model),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=45,
    )
    assert child.returncode == 0, child.stderr.decode(errors="replace")
    assert path.read_bytes() == source
    assert dataset.read_bytes() == data
    raw = json.loads(result.read_bytes())
    validated = validate_result_for_version(
        result,
        1024 * 1024,
        plan.model_dump(mode="json"),
        {"source": raw["population"]["source"], "eligible": raw["population"]["eligible"]},
        expected_source_sha256=source_hash,
    )
    assert validated == raw and raw["source_sha256"] == source_hash
    return raw, joblib.load(model)


@pytest.mark.parametrize("model", ["linear_regression", "ridge"])
@pytest.mark.parametrize("mixed", [False, True])
def test_real_generated_numeric_dense_and_mixed_sparse(tmp_path, model, mixed):
    plan, frame, data = plan_for(model, mixed=mixed)
    result, fitted = execute(tmp_path, plan, data)
    eligible = frame.loc[frame.y.notna()]
    X = eligible[[f.name for f in plan.features]]
    X_train, X_test, y_train, y_test = train_test_split(
        X, eligible.y, test_size=0.2, random_state=42
    )
    assert fitted.named_steps["model"].__class__.__name__ == plan.model.estimator
    actual_parameters = fitted.named_steps["model"].get_params(deep=False)
    assert all(
        actual_parameters[name] == value
        for name, value in plan.model.parameters.model_dump().items()
    )
    transformed = fitted.named_steps["preprocessor"].transform(X_test)
    assert sparse.issparse(transformed) == mixed
    branch = fitted.named_steps["preprocessor"].named_transformers_["feature_000"]
    assert branch.named_steps["step_0"].statistics_[0] == pytest.approx(X_train.x.mean())
    assert branch.named_steps["step_1"].mean_[0] == pytest.approx(X_train.x.mean())
    if mixed:
        encoder = (
            fitted.named_steps["preprocessor"]
            .named_transformers_["feature_001"]
            .named_steps["step_0"]
        )
        assert set(encoder.categories_[0]) == set(X_train.city)
        assert set(X_test.city).isdisjoint(encoder.categories_[0])
    predictions = fitted.predict(X_test)
    assert result["metrics"]["mae"] == pytest.approx(mean_absolute_error(y_test, predictions))
    assert result["metrics"]["mse"] == pytest.approx(mean_squared_error(y_test, predictions))
    assert result["metrics"]["rmse"] == pytest.approx(
        np.sqrt(mean_squared_error(y_test, predictions))
    )
    assert result["metrics"]["r2"] == pytest.approx(r2_score(y_test, predictions))
    assert not {"confusion_matrix", "positive_class", "roc_auc"} & set(result)


@pytest.mark.parametrize(
    "data,reason",
    [
        (b"x,y\n0,0\n1,0\n2,0\n3,0\n4,0\n5,0\n6,0\n7,0\n8,0\n9,0\n", "constant_test_target"),
        (b"x,y\n0,0\n1,1\n2,0\n3,\n", "test_population_too_small"),
    ],
)
def test_real_constant_zero_and_missing_two_valued_tiny_target(tmp_path, data, reason):
    plan, frame, data = plan_for(data=data)
    result, _ = execute(tmp_path, plan, data)
    assert result["population"]["eligible"] == int(frame.y.count())
    assert result["metrics"]["r2"] is None and result["r2_unavailable_reason"] == reason
    if reason == "constant_test_target":
        assert {k: result["metrics"][k] for k in ("mae", "mse", "rmse")} == dict.fromkeys(
            ["mae", "mse", "rmse"], 0.0
        )


def test_real_negative_r2(tmp_path):
    _, test = train_test_split(np.arange(20), test_size=0.2, random_state=42)
    values = {int(row): 100 + i for i, row in enumerate(test)}
    data = ("x,y\n" + "\n".join(f"{i},{values.get(i, 0)}" for i in range(20))).encode()
    plan, _, data = plan_for(data=data)
    result, _ = execute(tmp_path, plan, data)
    assert result["metrics"]["r2"] < 0 and result["r2_unavailable_reason"] is None


def test_dispatch_purity_order_literals_and_versions(monkeypatch):
    from mlstudio.codegen.dispatch import generate_for_version, load_plan, resolve_for_version

    ir, dataset, frame, _ = prepared()
    before = ir.model_dump()
    plan, _ = resolve_for_version(ir, dataset, "y", frame)
    ir.features = dict(reversed(list(ir.features.items())))
    same, _ = resolve_for_version(ir, dataset, "y", frame)
    assert plan.model_dump() == same.model_dump() and ir.model_dump() == before
    monkeypatch.setattr(
        Path, "read_bytes", lambda *_: (_ for _ in ()).throw(AssertionError("render reads source"))
    )
    source = generate_for_version(plan)
    assert source == generate_for_version(same) and "\r" not in source
    payload = plan.model_dump(mode="json")
    payload["features"][0]["name"] = "x'); __import__('os').abort(); #"
    safe = generate_for_version(load_plan(payload))
    constants = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in ast.parse(safe).body
        if isinstance(n, ast.Assign)
    }
    assert constants["FEATURES"] == [payload["features"][0]["name"]]
    compile(safe, "generated", "exec")
    for bad in [dict(payload, plan_version="99"), dict(payload, task="binary_classification")]:
        with pytest.raises(ValueError):
            load_plan(bad)


def test_resolved_plan_does_not_share_mutable_intent_binding():
    from mlstudio.codegen.dispatch import generate_for_version, resolve_for_version

    ir, dataset, frame, _ = prepared()
    plan, _ = resolve_for_version(ir, dataset, "y", frame)
    source = generate_for_version(plan)
    ir.dataset.fingerprint = "sha256:" + "f" * 64
    ir.model.parameters.fit_intercept = False
    assert generate_for_version(plan) == source


@pytest.mark.parametrize(
    "case", ["numeric", "l1", "decision_tree", "random_forest", "mixed", "unstratified"]
)
def test_binary_dispatch_keeps_original_goldens(case):
    from mlstudio.codegen.dispatch import generate_for_version

    assert (
        generate_for_version(golden_plan(case)).encode()
        == (GOLDENS / f"{case}.py.txt").read_bytes()
    )


@pytest.mark.parametrize("failure", ["source_changed", "environment"])
def test_generated_failure_preserves_source_and_emits_no_model(tmp_path, failure):
    from mlstudio.codegen.dispatch import generate_for_version, load_plan

    plan, _, data = plan_for()
    if failure == "environment":
        payload = plan.model_dump(mode="json")
        payload["implementation"]["python"] = "0.0.0"
        plan = load_plan(payload)
    source = generate_for_version(plan).encode()
    script, dataset = tmp_path / "generated_run.py", tmp_path / "private.csv"
    script.write_bytes(source)
    dataset.write_bytes(data + b"private sentinel" if failure == "source_changed" else data)
    result, model = tmp_path / "result.json", tmp_path / "model.joblib"
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(script),
            "--dataset",
            str(dataset),
            "--result",
            str(result),
            "--model",
            str(model),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=45,
    )
    assert child.returncode != 0 and not model.exists() and script.read_bytes() == source
    failed = json.loads(result.read_bytes())
    assert failed["schema_version"] == "mlstudio-result-v2" and failed["status"] == "failed"
    assert failed["stage"] == ("data_loading" if failure == "source_changed" else "runtime_inputs")
    assert b"private" not in child.stderr and "private" not in failed["message"]


def test_runtime_target_precision_and_nonfinite_metrics():
    import pandas as pd

    from mlstudio.codegen.v2.workload_runtime import evaluate_regression, numeric_target
    from mlstudio.codegen.workload_runtime import WorkloadValidationError

    for series in [
        pd.Series([True, False]),
        pd.Series(["a", "b"]),
        pd.Series([2**53 + 1, 3], dtype="Int64"),
        pd.Series([1.0, float("inf")]),
    ]:
        with pytest.raises(WorkloadValidationError):
            numeric_target(series)
    with np.errstate(over="ignore", invalid="ignore"), pytest.raises(WorkloadValidationError):
        evaluate_regression([1e308, -1e308], [-1e308, 1e308])


@pytest.mark.parametrize("case", REGRESSION_HASHES)
def test_regression_source_goldens(case):
    from mlstudio.codegen.dispatch import generate_for_version

    source = generate_for_version(regression_golden_plan(case))
    assert source.encode() == (GOLDENS / f"regression_v2_{case}.py.txt").read_bytes()
    assert hashlib.sha256(source.encode()).hexdigest() == REGRESSION_HASHES[case]
    assert "\r" not in source and source.endswith("\n") and not source.endswith("\n\n")
    assert "from mlstudio." not in source and "import mlstudio" not in source
    compile(source, "generated_run.py", "exec")
