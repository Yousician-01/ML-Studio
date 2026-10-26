"""Strict immutable v2 evidence and explicit result-version rejection."""

import json
from copy import deepcopy

import pytest
from regression_fixtures import plan_for
from test_run_results import protocol as binary_protocol  # noqa: F401 -- pytest fixture

from mlstudio.execution.results import ExecutionFailure


@pytest.fixture
def protocol():
    from mlstudio.codegen.v2.schemas import evaluation_context, plan_sha256

    plan, _, _ = plan_for()
    payload = plan.model_dump(mode="json")
    result = {
        "schema_version": "mlstudio-result-v2",
        "task": "regression",
        "status": "success",
        "dataset": payload["dataset"],
        "source": payload["source"],
        "generator": plan.generator,
        "implementation_version": plan.implementation.version,
        "plan_sha256": plan_sha256(plan),
        "source_sha256": "sha256:" + "b" * 64,
        "model": payload["model"],
        "evaluation": evaluation_context(plan),
        "metrics": {"mae": 1.0, "mse": 4.0, "rmse": 2.0, "r2": -0.5},
        "r2_unavailable_reason": None,
        "test_target_constant": False,
        "population": {"source": 20, "eligible": 20, "training": 16, "test": 4},
        "artifacts": {"model": {"kind": "complete_pipeline", "filename": "model.joblib"}},
        "versions": {"python": plan.implementation.python, **plan.implementation.libraries},
    }
    return payload, result


def validate(tmp_path, protocol):
    from mlstudio.execution.result_dispatch import validate_result_for_version

    plan, result = protocol
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return validate_result_for_version(
        path,
        1024 * 1024,
        plan,
        {"source": 20, "eligible": 20},
        expected_source_sha256="sha256:" + "b" * 64,
    )


def test_valid_negative_r2_and_zero_losses(tmp_path, protocol):
    assert validate(tmp_path, protocol) == protocol[1]
    protocol[1]["metrics"] = {"mae": 0.0, "mse": 0.0, "rmse": 0.0, "r2": 1.0}
    assert validate(tmp_path, protocol)["metrics"]["rmse"] == 0
    protocol[1].update(test_target_constant=True, r2_unavailable_reason="constant_test_target")
    protocol[1]["metrics"]["r2"] = None
    assert validate(tmp_path, protocol)["metrics"]["r2"] is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(schema_version="unknown"),
        lambda r: r.update(task="binary_classification"),
        lambda r: r.update(status="failed"),
        lambda r: r.update(confusion_matrix={}),
        lambda r: r.update(positive_class=1),
        lambda r: r.update(roc_auc=0.5),
        lambda r: r["metrics"].update(mae=None),
        lambda r: r["metrics"].update(mae=-1),
        lambda r: r["metrics"].update(mae=True),
        lambda r: r["metrics"].update(mae="1"),
        lambda r: r["metrics"].update(mse=float("inf")),
        lambda r: r["metrics"].update(rmse=float("nan")),
        lambda r: r["metrics"].update(rmse=3),
        lambda r: r["metrics"].update(r2=1.1),
        lambda r: r["metrics"].update(r2=None),
        lambda r: r.update(r2_unavailable_reason="invented"),
        lambda r: r.update(test_target_constant=True),
        lambda r: r["population"].update(test=True),
        lambda r: r["population"].update(eligible=19),
        lambda r: r["population"].update(training=15),
        lambda r: r["model"]["parameters"].update(fit_intercept=False),
        lambda r: r["evaluation"]["split"].update(random_seed=5),
        lambda r: r["evaluation"]["target"].update(column="other"),
        lambda r: r["source"].update(size_bytes=1),
        lambda r: r["dataset"].update(fingerprint="bad"),
        lambda r: r.update(source_sha256="sha256:" + "c" * 64),
        lambda r: r.update(plan_sha256="sha256:" + "d" * 64),
        lambda r: r.update(implementation_version="unknown"),
        lambda r: r["versions"].update(numpy="0"),
        lambda r: r["artifacts"]["model"].update(filename="../model.joblib"),
    ],
)
def test_invalid_result_rejected(tmp_path, protocol, mutate):
    plan, result = protocol
    result = deepcopy(result)
    mutate(result)
    with pytest.raises(ExecutionFailure, match="result_invalid"):
        validate(tmp_path, (plan, result))


@pytest.mark.parametrize("data", [b"{", b'{"a":1,"a":2}', b"{}", b'{"a":NaN}'])
def test_malformed_result(tmp_path, protocol, data):
    from mlstudio.execution.result_dispatch import validate_result_for_version

    path = tmp_path / "result.json"
    path.write_bytes(data)
    with pytest.raises(ExecutionFailure, match="result_invalid"):
        validate_result_for_version(
            path,
            1000,
            protocol[0],
            {"source": 20, "eligible": 20},
            expected_source_sha256="sha256:" + "b" * 64,
        )


def test_binary_result_dispatch_and_unknown_plan_protocol(tmp_path, binary_protocol):  # noqa: F811
    from test_codegen import golden_plan

    from mlstudio.execution.result_dispatch import validate_result_for_version

    _, result = binary_protocol
    plan = golden_plan("numeric").model_dump(mode="json")
    result.update(
        dataset=plan["dataset"],
        generator=plan["generator"],
        versions={
            "python": plan["implementation"]["python"],
            **plan["implementation"]["libraries"],
        },
    )
    result["confusion_matrix"]["labels"] = [
        plan["target"]["negative_class"],
        plan["target"]["positive_class"],
    ]
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert validate_result_for_version(path, 10000, plan, {"source": 22, "eligible": 20}) == result
    for mutation in [
        {"plan_version": "unknown"},
        {"runtime": {"result_schema": "unknown"}},
        {"runtime": None},
        {"runtime": []},
        {"task": "regression"},
        {"ir_version": "unknown"},
        {"model": {"type": "ridge"}},
    ]:
        with pytest.raises(ExecutionFailure, match="result_invalid"):
            validate_result_for_version(
                path, 10000, {**plan, **mutation}, {"source": 22, "eligible": 20}
            )


def test_missing_bounded_result_and_missing_source_hash(tmp_path, protocol):
    from mlstudio.execution.result_dispatch import validate_result_for_version

    plan, result = protocol
    path = tmp_path / "result.json"
    with pytest.raises(ExecutionFailure, match="result_missing"):
        validate_result_for_version(
            path, 100, plan, {}, expected_source_sha256=result["source_sha256"]
        )
    path.write_bytes(b" " * 101)
    with pytest.raises(ExecutionFailure, match="result_invalid"):
        validate_result_for_version(
            path, 100, plan, {}, expected_source_sha256=result["source_sha256"]
        )
    with pytest.raises(ExecutionFailure, match="result_invalid"):
        validate_result_for_version(path, 100, plan, {})
