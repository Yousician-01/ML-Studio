"""Inspectable helpers embedded in generated source; preview never calls the workload."""

import hashlib
import json
import os
import platform
import tempfile
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.utils.multiclass import type_of_target


class WorkloadValidationError(ValueError):
    """Only fixed, source-independent messages may use this exception."""


def scalar_record(value):
    if hasattr(value, "item"):
        value = value.item()
    kind = {str: "string", int: "integer", float: "float", bool: "boolean"}.get(type(value))
    if kind is None or (kind == "float" and not np.isfinite(value)):
        raise ValueError("Unsupported target scalar.")
    if kind == "integer" and abs(value) > 2**53 - 1:
        value = str(value)
    return {"value_type": kind, "value": value}


def verify_environment(libraries, python):
    if platform.python_version() != python:
        raise ValueError("Python version differs from the resolved plan.")
    if any(version(name) != expected for name, expected in libraries.items()):
        raise ValueError("Library versions differ from the resolved plan.")


def read_verified_bytes(path, expected_fingerprint, expected_size):
    # Hash and parse this same bounded byte buffer, not a path reopened after hashing.
    with Path(path).open("rb") as stream:
        data = stream.read(expected_size + 1)
    if len(data) != expected_size:
        raise ValueError("Dataset size differs from the resolved source.")
    if "sha256:" + hashlib.sha256(data).hexdigest() != expected_fingerprint:
        raise ValueError("Dataset fingerprint does not match the resolved source.")
    return data


def validate_target(target, positive, negative):
    classes = [scalar_record(v) for v in target.dropna().unique()]
    if (
        len(classes) != 2
        or positive not in classes
        or negative not in classes
        or positive == negative
    ):
        raise ValueError("Target must match the two resolved typed classes.")
    if type_of_target(target.dropna()) != "binary":
        raise ValueError("Unsupported sklearn target representation; labels were not converted.")


def validate_training_partition(X_train, y_train):
    if y_train.nunique() != 2:
        raise WorkloadValidationError(
            "Training partition must contain both target classes. Review the split."
        )
    if X_train.isna().all().any():
        raise WorkloadValidationError(
            "A training feature has no observed values; cannot learn its statistic."
        )


def evaluate_predictions(model_pipeline, X_test, y_test, predictions, positive, negative):
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(
            precision_score(y_test, predictions, pos_label=positive, zero_division=0)
        ),
        "recall": float(recall_score(y_test, predictions, pos_label=positive, zero_division=0)),
        "f1": float(f1_score(y_test, predictions, pos_label=positive, zero_division=0)),
        "roc_auc": None,
    }
    matrix = confusion_matrix(y_test, predictions, labels=[negative, positive]).tolist()
    reason = None
    if y_test.nunique() < 2:
        reason = "Held-out target contains only one class."
    else:
        classes = [scalar_record(v) for v in model_pipeline.classes_]
        positive_record = scalar_record(positive)
        if len(classes) != 2 or positive_record not in classes:
            raise ValueError("Fitted class orientation does not match the resolved target.")
        index = classes.index(positive_record)
        scores = None
        if hasattr(model_pipeline, "predict_proba"):
            scores = model_pipeline.predict_proba(X_test)[:, index]
        elif hasattr(model_pipeline, "decision_function"):
            scores = model_pipeline.decision_function(X_test)
            if index == 0:
                scores = -scores
        if scores is None:
            reason = "No compatible continuous score is available."
        else:
            # Metric orientation only; original training and predicted labels are unchanged.
            metrics["roc_auc"] = float(roc_auc_score(y_test == positive, scores))
    return metrics, matrix, reason


def write_result(destination, result):
    # Encoding first prevents a NaN/Infinity result from becoming a successful artifact.
    payload = (
        json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n"
    )
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_model(destination, model_pipeline):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=Path(destination).parent, delete=False) as stream:
            temporary = Path(stream.name)
        joblib.dump(model_pipeline, temporary, compress=3, protocol=5)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def runtime_paths(dataset, result, model):
    paths = [Path(value) for value in (dataset, result, model)]
    if not all(p.is_absolute() for p in paths):
        raise ValueError("Supply absolute runtime paths; working-directory discovery is disabled.")
    paths = [p.resolve() for p in paths]
    if len(set(paths)) != 3 or any(p.exists() for p in paths[1:]):
        raise ValueError(
            "Output destinations must be distinct new files, separate from the source."
        )
    if not all(p.parent.is_dir() for p in paths[1:]):
        raise ValueError("The executor must prepare output directories before launch.")
    return paths
