"""Code Mode reporting v1. Copied as mlstudio_runtime.py into each execution workspace.

Only aggregates are written; predictions and targets are never retained. This module
has no backend imports and works with the configured Python interpreter.
"""

import json
import math
import os
from pathlib import Path

SCHEMA = "mlstudio-code-report-v1"
MULTICLASS_SCHEMA = "mlstudio-code-report-v2"
MAX_BYTES = 1024 * 1024
MAX_SAMPLES = 100_000
_report = {"schema_version": SCHEMA, "evaluation": None, "metrics": {}, "outputs": {}}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError("Unexpected reporting fields.")


def _json_value(value, depth=0):
    if depth > 8:
        raise ValueError("Output nesting exceeds eight levels.")
    if value is None or type(value) is bool or _number(value):
        return
    if type(value) is str and len(value) <= 8192:
        return
    if type(value) is list and len(value) <= 256:
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict and len(value) <= 64:
        for key, item in value.items():
            _name(key)
            _json_value(item, depth + 1)
        return
    raise ValueError("Output must be bounded, finite JSON-compatible data.")


def _name(value):
    if type(value) is not str or not value.strip() or len(value) > 128:
        raise ValueError("Reporting names must contain 1–128 characters.")


def _scalar(value):
    if hasattr(value, "item"):
        value = value.item()
    kind = {str: "string", int: "integer", float: "float", bool: "boolean"}.get(type(value))
    if kind is None or (kind == "float" and not math.isfinite(value)):
        raise ValueError("Class labels must be finite typed scalars.")
    if kind == "string" and len(value) > 1024:
        raise ValueError("Class labels exceed their bound.")
    if kind == "integer" and abs(value) > 2**53 - 1:
        value = str(value)
    return {"value_type": kind, "value": value}


def validate_report(report, task):
    """Strict structural/aggregate checks for untrusted subprocess JSON."""
    _fields(report, "schema_version evaluation metrics outputs")
    if report["schema_version"] not in (SCHEMA, MULTICLASS_SCHEMA):
        raise ValueError("Unsupported Code reporting version.")
    for key in ("metrics", "outputs"):
        if type(report[key]) is not dict or len(report[key]) > 64:
            raise ValueError("At most 64 custom metrics and outputs are supported.")
        for name, value in report[key].items():
            _name(name)
            if key == "metrics" and not _number(value):
                raise ValueError("Custom metrics must be finite numbers.")
            _json_value(value)
    result = report["evaluation"]
    if report["schema_version"] == MULTICLASS_SCHEMA:
        if task != "multiclass_classification" or result is None:
            raise ValueError("Multiclass reporting requires the originating multiclass task.")
        validate_multiclass_evaluation(result)
        return report
    if result is None:
        return report
    if task not in ("binary_classification", "regression") or result.get("task") != task:
        raise ValueError("Reported task differs from the Code Run task.")
    common = "task metrics population "
    if task == "binary_classification":
        _fields(result, common + "confusion_matrix roc_auc_unavailable_reason")
    else:
        _fields(result, common + "r2_unavailable_reason")
    _fields(result["population"], "test")
    count = result["population"]["test"]
    if type(count) is not int or not 1 <= count <= MAX_SAMPLES:
        raise ValueError("Reported evaluation population exceeds its bound.")
    metrics = result["metrics"]
    if task == "binary_classification":
        _fields(metrics, "accuracy precision recall f1 roc_auc")
        matrix = result["confusion_matrix"]
        _fields(matrix, "labels values")
        labels, cells = matrix["labels"], matrix["values"]
        if type(labels) is not list or len(labels) != 2:
            raise ValueError("Exactly two typed classes are required.")
        # Validate lossless JSON class encoding, including unsafe integer strings.
        for label in labels:
            _fields(label, "value_type value")
            value = label["value"]
            if label["value_type"] == "integer" and type(value) is str:
                converted = int(value)
                if str(converted) != value or abs(converted) <= 2**53 - 1:
                    raise ValueError("Invalid integer class encoding.")
                value = converted
            if _scalar(value) != label:
                raise ValueError("Invalid class scalar type.")
        if labels[0] == labels[1] or labels[0]["value_type"] != labels[1]["value_type"]:
            raise ValueError("Classes must be distinct and have matching scalar types.")
        if (
            type(cells) is not list
            or len(cells) != 2
            or any(type(row) is not list or len(row) != 2 for row in cells)
            or any(type(v) is not int or v < 0 for row in cells for v in row)
        ):
            raise ValueError("Invalid confusion matrix.")
        tn, fp = cells[0]
        fn, tp = cells[1]
        if tn + fp + fn + tp != count:
            raise ValueError("Confusion counts do not match population.")
        expected = {
            "accuracy": (tn + tp) / count,
            "precision": tp / (tp + fp) if tp + fp else 0,
            "recall": tp / (tp + fn) if tp + fn else 0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        }
        for name, number in expected.items():
            if not _number(metrics[name]) or not math.isclose(metrics[name], number, abs_tol=1e-12):
                raise ValueError("Metrics do not match confusion counts.")
        auc, reason = metrics["roc_auc"], result["roc_auc_unavailable_reason"]
        expected_reason = (
            "Held-out target contains only one class."
            if not (tn + fp and fn + tp)
            else "No compatible continuous score is available."
        )
        if auc is None:
            if reason != expected_reason:
                raise ValueError("Invalid AUC availability reason.")
        elif (
            not _number(auc) or not 0 <= auc <= 1 or reason is not None or not (tn + fp and fn + tp)
        ):
            raise ValueError("Invalid AUC.")
    else:
        _fields(metrics, "mae mse rmse r2")
        for key in ("mae", "mse", "rmse"):
            if not _number(metrics[key]) or metrics[key] < 0:
                raise ValueError("Regression losses must be finite and nonnegative.")
        if not math.isclose(metrics["rmse"], math.sqrt(metrics["mse"]), abs_tol=1e-12):
            raise ValueError("RMSE must match MSE.")
        r2, reason = metrics["r2"], result["r2_unavailable_reason"]
        if r2 is None:
            if reason not in ("test_population_too_small", "constant_test_target"):
                raise ValueError("Missing R² needs an availability reason.")
            if (count < 2) != (reason == "test_population_too_small"):
                raise ValueError("Invalid R² population.")
        elif not _number(r2) or r2 > 1 or reason is not None or count < 2:
            raise ValueError("Invalid R².")
    return report


def _publish(**changes):
    global _report
    report = {**_report, **changes}
    evaluation = report["evaluation"]
    report["schema_version"] = (
        MULTICLASS_SCHEMA
        if evaluation and evaluation["task"] == "multiclass_classification"
        else SCHEMA
    )
    validate_report(report, evaluation["task"] if evaluation else None)
    data = json.dumps(report, allow_nan=False, ensure_ascii=True, sort_keys=True).encode()
    if len(data) > MAX_BYTES:
        raise ValueError("Code reporting exceeds 1 MiB.")
    path = Path(os.environ.get("MLSTUDIO_EVALUATION_PATH", "code-evaluation.json"))
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
    _report = report


def _arrays(y_true, y_pred, *, numeric=False):
    import numpy as np

    # Object arrays preserve scalar meaning before coercion (bool is not a regression number).
    actual, predicted = np.asarray(y_true, dtype=object), np.asarray(y_pred, dtype=object)
    if actual.ndim != 1 or predicted.shape != actual.shape or not 1 <= actual.size <= MAX_SAMPLES:
        raise ValueError("Report matching one-dimensional arrays of 1–100,000 values.")
    if numeric:
        if any(
            not _number(v.item() if hasattr(v, "item") else v)
            for values in (actual, predicted)
            for v in values
        ):
            raise ValueError("Regression requires finite numeric values, without missing data.")
        return actual.astype(float), predicted.astype(float)
    return actual, predicted


def classification_scores(model, features, positive_class):
    """Optional score orientation helper for the generated Code Mode baseline."""
    classes = [_scalar(value) for value in model.classes_]
    if len(classes) != 2 or _scalar(positive_class) not in classes:
        raise ValueError("Model class orientation is incompatible.")
    index = classes.index(_scalar(positive_class))
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, index]
    if hasattr(model, "decision_function"):
        scores = model.decision_function(features)
        return -scores if index == 0 else scores
    return None


def report_classification(*, y_true, y_pred, labels, scores=None):
    """labels=[negative, positive]; scores must increase toward the positive class."""
    import numpy as np
    from sklearn.metrics import roc_auc_score

    if len(labels) >= 3:
        if scores is not None:
            raise ValueError("Multiclass ROC-AUC and scores are not supported.")
        _publish(evaluation=multiclass_evaluation(y_true, y_pred, labels))
        return
    actual, predicted = _arrays(y_true, y_pred)
    if len(labels) != 2:
        raise ValueError("Exactly two labels in negative/positive order are required.")
    labels = [_scalar(value) for value in labels]
    encoded = []
    for values in (actual, predicted):
        indices = []
        for value in values:
            label = _scalar(value)
            if label not in labels:
                raise ValueError("Observed class is outside the two declared typed labels.")
            indices.append(labels.index(label))
        encoded.append(np.asarray(indices))
    cells = [
        [int(np.sum((encoded[0] == i) & (encoded[1] == j))) for j in range(2)] for i in range(2)
    ]
    tn, fp = cells[0]
    fn, tp = cells[1]
    auc = None
    reason = (
        "Held-out target contains only one class."
        if len(np.unique(encoded[0])) < 2
        else "No compatible continuous score is available."
    )
    if scores is not None:
        _, values = _arrays(y_true, scores, numeric=False)
        if any(not _number(v.item() if hasattr(v, "item") else v) for v in values):
            raise ValueError("Scores must be finite numeric values.")
        if len(np.unique(encoded[0])) == 2:
            auc, reason = float(roc_auc_score(encoded[0], values.astype(float))), None
    _publish(
        evaluation={
            "task": "binary_classification",
            "population": {"test": len(actual)},
            "metrics": {
                "accuracy": (tn + tp) / len(actual),
                "precision": tp / (tp + fp) if tp + fp else 0,
                "recall": tp / (tp + fn) if tp + fn else 0,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
                "roc_auc": auc,
            },
            "roc_auc_unavailable_reason": reason,
            "confusion_matrix": {"labels": labels, "values": cells},
        }
    )


def report_regression(*, y_true, y_pred):
    import numpy as np
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    actual, predicted = _arrays(y_true, y_pred, numeric=True)
    mse = float(mean_squared_error(actual, predicted))
    reason = (
        "test_population_too_small"
        if len(actual) < 2
        else "constant_test_target"
        if np.all(actual == actual[0])
        else None
    )
    _publish(
        evaluation={
            "task": "regression",
            "population": {"test": len(actual)},
            "metrics": {
                "mae": float(mean_absolute_error(actual, predicted)),
                "mse": mse,
                "rmse": math.sqrt(mse),
                "r2": None if reason else float(r2_score(actual, predicted, force_finite=False)),
            },
            "r2_unavailable_reason": reason,
        }
    )


def report_metric(name, value):
    if hasattr(value, "item"):
        value = value.item()
    _publish(metrics={**_report["metrics"], name: value})


def report_output(name, value):
    _publish(outputs={**_report["outputs"], name: value})


def reporting_block(task):
    if task == "regression":
        reporting = (
            "        from mlstudio_runtime import report_regression\n"
            "        report_regression(y_true=y_test, y_pred=predictions)\n"
        )
    elif task == "multiclass_classification":
        reporting = (
            "        from mlstudio_runtime import report_classification\n"
            "        report_classification(y_true=y_test, y_pred=predictions, labels=CLASSES)\n"
        )
    else:
        reporting = (
            "        from mlstudio_runtime import report_classification, classification_scores\n"
            "        report_classification(\n"
            "            y_true=y_test, y_pred=predictions,\n"
            "            labels=[NEGATIVE_CLASS, POSITIVE_CLASS],\n"
            "            scores=classification_scores(model_pipeline, X_test, POSITIVE_CLASS),\n"
            "        )\n"
        )
    return reporting


def code_mode_source(source, task):
    """Only known generated source is instrumented; visual renderer is untouched."""
    marker = "        result = {"
    reporting = reporting_block(task)
    if "\r\n" in source:
        reporting = reporting.replace("\n", "\r\n")
    if reporting in source:
        return source
    if source.count(marker) != 1:
        raise ValueError("Generated Code Mode integration point is unavailable.")
    return source.replace(marker, reporting + marker)


def multiclass_labels(labels):
    """Homogeneous typed labels, explicit deterministic order and a bounded universe."""
    values = [v.item() if hasattr(v, "item") else v for v in labels]
    if (
        not 3 <= len(values) <= 50
        or len({type(v) for v in values}) != 1
        or type(values[0]) not in (str, int, bool)
        or len(set(values)) != len(values)
        or values != sorted(values)
    ):
        raise ValueError(
            "Use 3–50 distinct homogeneous string/integer/Boolean labels in sorted order."
        )
    return [_scalar(v) for v in values]


def multiclass_evaluation(y_true, y_pred, labels):
    from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

    typed = multiclass_labels(labels)
    actual, predicted = _arrays(y_true, y_pred)
    encoded = []
    for values in (actual, predicted):
        indices = []
        for value in values:
            record = _scalar(value)
            if record not in typed:
                raise ValueError("Observed class is outside the declared typed label universe.")
            indices.append(typed.index(record))
        encoded.append(indices)
    order = list(range(len(labels)))
    precision, recall, f1, support = precision_recall_fscore_support(
        *encoded, labels=order, zero_division=0
    )
    metrics = {"accuracy": float(accuracy_score(*encoded))}
    for average in ("macro", "weighted"):
        p, r, f, _ = precision_recall_fscore_support(
            *encoded, labels=order, average=average, zero_division=0
        )
        metrics.update(
            {
                f"precision_{average}": float(p),
                f"recall_{average}": float(r),
                f"f1_{average}": float(f),
            }
        )
    return {
        "task": "multiclass_classification",
        "metrics": metrics,
        "population": {"test": len(actual)},
        "confusion_matrix": {
            "labels": typed,
            "values": confusion_matrix(*encoded, labels=order).tolist(),
        },
        "per_class": [
            {
                "label": label,
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i, label in enumerate(typed)
        ],
    }


def validate_multiclass_evaluation(result):
    _fields(result, "task metrics population confusion_matrix per_class")
    if result["task"] != "multiclass_classification":
        raise ValueError("Incompatible multiclass task.")
    _fields(result["population"], "test")
    count = result["population"]["test"]
    if type(count) is not int or not 1 <= count <= MAX_SAMPLES:
        raise ValueError("Invalid multiclass evaluation population.")
    matrix = result["confusion_matrix"]
    _fields(matrix, "labels values")
    labels = matrix["labels"]
    if type(labels) is not list or not 3 <= len(labels) <= 50:
        raise ValueError("Invalid class universe.")
    values = []
    for label in labels:
        _fields(label, "value_type value")
        value = label["value"]
        if label["value_type"] == "integer" and type(value) is str:
            value = int(value)
        if _scalar(value) != label:
            raise ValueError("Invalid typed class.")
        values.append(value)
    if multiclass_labels(values) != labels:
        raise ValueError("Class ordering is inconsistent.")
    n, cells = len(labels), matrix["values"]
    if (
        type(cells) is not list
        or len(cells) != n
        or any(type(row) is not list or len(row) != n for row in cells)
        or any(type(v) is not int or v < 0 for row in cells for v in row)
        or sum(map(sum, cells)) != count
    ):
        raise ValueError("Invalid multiclass confusion counts.")
    per_class = result["per_class"]
    if type(per_class) is not list or len(per_class) != n:
        raise ValueError("Invalid per-class metrics.")
    expected = {
        "accuracy": sum(cells[i][i] for i in range(n)) / count,
        **{
            f"{metric}_{average}": 0.0
            for metric in ("precision", "recall", "f1")
            for average in ("macro", "weighted")
        },
    }
    for i, record in enumerate(per_class):
        _fields(record, "label precision recall f1 support")
        support = sum(cells[i])
        predicted = sum(row[i] for row in cells)
        tp = cells[i][i]
        scores = {
            "precision": tp / predicted if predicted else 0,
            "recall": tp / support if support else 0,
            "f1": 2 * tp / (support + predicted) if support + predicted else 0,
        }
        if (
            json.dumps(record["label"], sort_keys=True, allow_nan=False)
            != json.dumps(labels[i], sort_keys=True, allow_nan=False)
            or type(record["support"]) is not int
            or record["support"] != support
        ):
            raise ValueError("Per-class support or orientation differs.")
        for key, value in scores.items():
            if not _number(record[key]) or not math.isclose(record[key], value, abs_tol=1e-12):
                raise ValueError("Per-class metrics do not match counts.")
            expected[f"{key}_macro"] += value / n
            expected[f"{key}_weighted"] += value * support / count
    _fields(result["metrics"], " ".join(expected))
    for key, value in expected.items():
        if not _number(result["metrics"][key]) or not math.isclose(
            result["metrics"][key], value, abs_tol=1e-12
        ):
            raise ValueError("Aggregate multiclass metrics do not match counts.")
    return result
