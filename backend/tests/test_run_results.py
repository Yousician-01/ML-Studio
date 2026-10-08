import copy
import json

import pytest

from mlstudio.execution.artifacts import strict_json
from mlstudio.execution.results import ExecutionFailure, validate_result


@pytest.fixture
def protocol():
    negative = {"value_type": "integer", "value": 2}
    positive = {"value_type": "integer", "value": 1}
    plan = {
        "dataset": {"dataset_id": "test", "fingerprint": "sha256:abc"},
        "generator": "mlstudio-python-v1",
        "implementation": {"python": "3", "libraries": {"numpy": "2"}},
        "target": {"negative_class": negative, "positive_class": positive},
        "split": {"test_size": 0.2},
    }
    result = {
        "schema_version": "mlstudio-result-v1",
        "status": "success",
        "dataset": plan["dataset"],
        "generator": plan["generator"],
        "versions": {"python": "3", "numpy": "2"},
        "metrics": {"accuracy": 0.75, "precision": 1.0, "recall": 0.5, "f1": 2 / 3, "roc_auc": 0.8},
        "roc_auc_unavailable_reason": None,
        "confusion_matrix": {"labels": [negative, positive], "values": [[2, 0], [1, 1]]},
        "population": {"source": 22, "eligible": 20, "training": 16, "test": 4},
        "artifacts": {"model": {"kind": "complete_pipeline", "filename": "model.joblib"}},
    }
    return plan, result


def test_valid_result(tmp_path, protocol):
    plan, result = protocol
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    assert validate_result(path, 10000, plan, {"source": 22, "eligible": 20}) == result


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(extra="bad"),
        lambda r: r.update(status="failed"),
        lambda r: r.update(schema_version="unknown"),
        lambda r: r.update(generator="other"),
        lambda r: r["dataset"].update(dataset_id="other"),
        lambda r: r["dataset"].update(fingerprint="bad"),
        lambda r: r["versions"].update(numpy="other"),
        lambda r: r["confusion_matrix"].update(
            labels=list(reversed(r["confusion_matrix"]["labels"]))
        ),
        lambda r: r["confusion_matrix"]["labels"][0].update(value=True),
        lambda r: r["confusion_matrix"].update(values=[[True, 0], [1, 1]]),
        lambda r: r["confusion_matrix"].update(values=[[-1, 3], [1, 1]]),
        lambda r: r["confusion_matrix"].update(values=[[2, 0, 0], [1, 1]]),
        lambda r: r["confusion_matrix"].update(values=[[2.0, 0], [1, 1]]),
        lambda r: r["confusion_matrix"].update(values=[[2, 1], [1, 1]]),
        lambda r: r["population"].update(source=23),
        lambda r: r["population"].update(eligible=21),
        lambda r: r["population"].update(training=17),
        lambda r: r["population"].update(test=5),
        lambda r: r["population"].update(test=True),
        lambda r: r["metrics"].update(accuracy=0.5),
        lambda r: r["metrics"].update(precision=0.5),
        lambda r: r["metrics"].update(recall=0.6),
        lambda r: r["metrics"].update(f1=0.5),
        lambda r: r["metrics"].update(roc_auc=2),
        lambda r: r["metrics"].update(roc_auc=float("inf")),
        lambda r: r["metrics"].update(accuracy=True),
        lambda r: r["metrics"].update(roc_auc=None),
        lambda r: r.update(roc_auc_unavailable_reason="invented"),
        lambda r: r["artifacts"]["model"].update(filename="../model.joblib"),
        lambda r: r["artifacts"]["model"].update(kind="classifier"),
    ],
)
def test_invalid_result(tmp_path, protocol, mutation):
    plan, result = protocol
    result = copy.deepcopy(result)
    mutation(result)
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ExecutionFailure, match="result_invalid"):
        validate_result(path, 10000, plan, {"source": 22, "eligible": 20})


@pytest.mark.parametrize(
    "data", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b"{"]
)
def test_strict_json(data):
    with pytest.raises(ValueError):
        strict_json(data)


def test_missing_and_oversized_result(tmp_path, protocol):
    plan, _ = protocol
    path = tmp_path / "result.json"
    with pytest.raises(ExecutionFailure, match="result_missing"):
        validate_result(path, 10, plan, {})
    path.write_bytes(b" " * 11)
    with pytest.raises(ExecutionFailure, match="result_invalid"):
        validate_result(path, 10, plan, {})
