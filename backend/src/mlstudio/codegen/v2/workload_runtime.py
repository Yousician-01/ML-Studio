"""Regression-only standalone helpers; shared I/O comes from the unchanged v1 runtime."""

import math

import numpy as np
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from mlstudio.codegen.workload_runtime import WorkloadValidationError


def numeric_target(series):
    if (
        not is_numeric_dtype(series.dtype)
        or is_bool_dtype(series.dtype)
        or is_complex_dtype(series.dtype)
        or series.empty
        or series.isna().any()
    ):
        raise WorkloadValidationError("Regression requires observed numeric, non-Boolean targets.")
    for value in series.unique():
        value = value.item() if hasattr(value, "item") else value
        if not math.isfinite(value):
            raise WorkloadValidationError("Regression target values must be finite.")
        if isinstance(value, int) and int(float(value)) != value:
            raise WorkloadValidationError("Regression target precision cannot safely convert.")
    return series.to_numpy(dtype=np.float64)


def validate_regression_training(X_train, y_train, y_test):
    if len(y_train) < 2 or len(y_test) < 1:
        raise WorkloadValidationError("Regression needs two training rows and one test row.")
    if X_train.isna().all().any():
        raise WorkloadValidationError("A training feature has no observed values.")


def evaluate_regression(y_test, predictions):
    actual = np.asarray(y_test, dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.float64)
    if (
        actual.ndim != 1
        or predicted.shape != actual.shape
        or not actual.size
        or not np.isfinite(actual).all()
        or not np.isfinite(predicted).all()
    ):
        raise WorkloadValidationError("Regression evaluation requires finite scalar predictions.")
    mse = float(mean_squared_error(actual, predicted))
    metrics = {
        "mae": float(mean_absolute_error(actual, predicted)),
        "mse": mse,
        "rmse": math.sqrt(mse),
        "r2": None,
    }
    constant = bool(np.all(actual == actual[0]))
    if len(actual) < 2:
        reason = "test_population_too_small"
    elif constant:
        reason = "constant_test_target"
    else:
        reason = None
        metrics["r2"] = float(r2_score(actual, predicted, force_finite=False))
    if any(value is not None and not math.isfinite(value) for value in metrics.values()):
        raise WorkloadValidationError("Regression metrics must be finite.")
    return metrics, reason, constant
