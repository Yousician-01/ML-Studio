"""Validate the existing workload protocol without loading executable model bytes."""

import math

from mlstudio.execution.artifacts import bounded_read, strict_json


class ExecutionFailure(Exception):
    def __init__(self, code: str, stage: str = "execution"):
        self.code = code
        self.stage = stage
        super().__init__(code)


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError("Unexpected result fields.")


def validate_result(path, limit, plan, population):
    try:
        result = strict_json(bounded_read(path, limit))
    except FileNotFoundError:
        raise ExecutionFailure("result_missing", "result") from None
    except (ValueError, OSError, RecursionError):
        raise ExecutionFailure("result_invalid", "result") from None
    try:
        fields(
            result,
            "schema_version status dataset generator metrics roc_auc_unavailable_reason "
            "confusion_matrix population artifacts versions",
        )
        if result["schema_version"] != "mlstudio-result-v1" or result["status"] != "success":
            raise ValueError()
        if result["dataset"] != plan["dataset"] or result["generator"] != plan["generator"]:
            raise ValueError()
        if result["versions"] != {
            "python": plan["implementation"]["python"],
            **plan["implementation"]["libraries"],
        }:
            raise ValueError()
        matrix = result["confusion_matrix"]
        fields(matrix, "labels values")
        # Canonical encoding distinguishes bool/int/float typed scalar values.
        from mlstudio.execution.artifacts import canonical

        if canonical(matrix["labels"]) != canonical(
            [plan["target"]["negative_class"], plan["target"]["positive_class"]]
        ):
            raise ValueError()
        cells = matrix["values"]
        if (
            not isinstance(cells, list)
            or len(cells) != 2
            or any(not isinstance(row, list) or len(row) != 2 for row in cells)
        ):
            raise ValueError()
        if any(type(value) is not int or value < 0 for row in cells for value in row):
            raise ValueError()
        counts = result["population"]
        fields(counts, "source eligible training test")
        if any(type(value) is not int or value <= 0 for value in counts.values()):
            raise ValueError()
        expected_test = math.ceil(population["eligible"] * plan["split"]["test_size"])
        if counts != {
            **population,
            "test": expected_test,
            "training": population["eligible"] - expected_test,
        }:
            raise ValueError()
        tn, fp = cells[0]
        fn, tp = cells[1]
        if tn + fp + fn + tp != counts["test"]:
            raise ValueError()
        metrics = result["metrics"]
        fields(metrics, "accuracy precision recall f1 roc_auc")
        expected = {
            "accuracy": (tn + tp) / counts["test"],
            "precision": tp / (tp + fp) if tp + fp else 0,
            "recall": tp / (tp + fn) if tp + fn else 0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        }
        for name, value in metrics.items():
            if name == "roc_auc" and value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError()
            if name in expected and not math.isclose(
                value, expected[name], rel_tol=1e-9, abs_tol=1e-12
            ):
                raise ValueError()
        reason = result["roc_auc_unavailable_reason"]
        if metrics["roc_auc"] is None:
            if reason not in (
                "Held-out target contains only one class.",
                "No compatible continuous score is available.",
            ):
                raise ValueError()
            if reason == "Held-out target contains only one class." and tn + fp and fn + tp:
                raise ValueError()
        elif reason is not None or not (tn + fp and fn + tp):
            raise ValueError()
        if result["artifacts"] != {
            "model": {"kind": "complete_pipeline", "filename": "model.joblib"}
        }:
            raise ValueError()
        return result
    except (ValueError, KeyError, TypeError, OverflowError):
        raise ExecutionFailure("result_invalid", "result") from None


def failure_stage(path, limit):
    """Only accept documented structural failure stages; never copy child messages."""
    try:
        result = strict_json(bounded_read(path, limit))
        fields(result, "schema_version status stage message")
        if (
            result["schema_version"] == "mlstudio-result-v1"
            and result["status"] == "failed"
            and result["stage"]
            in {
                "runtime_inputs",
                "data_loading",
                "target",
                "split",
                "preprocessing",
                "training_partition_validation",
                "training",
                "evaluation",
                "artifact_output",
            }
        ):
            return result["stage"]
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    return "execution"
