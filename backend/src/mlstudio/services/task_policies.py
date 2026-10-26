"""Target observations only. Never coerce, impute, fit, or choose a task from data."""

import math

from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

from mlstudio.services.source import DomainError, target_classes


def validate_target_for_task(frame, column, task):
    if task == "binary_classification":
        return target_classes(frame, column)
    if task != "regression":
        raise DomainError("Unsupported Project objective.")
    if column not in frame:
        raise DomainError("Target must belong to the active Dataset.")
    series = frame[column]
    if (
        not is_numeric_dtype(series.dtype)
        or is_bool_dtype(series.dtype)
        or is_complex_dtype(series.dtype)
    ):
        raise DomainError("Regression requires a numeric, non-Boolean target.")
    observed = series.dropna()
    if observed.empty:
        raise DomainError("Regression target needs at least one non-missing numeric value.")
    # Future sklearn regression uses float64. Do not silently round parsed integers.
    # Compare the actual conversion rather than rejecting all integers above 2**53.
    for value in observed.unique():
        value = value.item() if hasattr(value, "item") else value
        if not math.isfinite(value):
            raise DomainError("Regression target values must be finite.")
        if isinstance(value, int) and int(float(value)) != value:
            raise DomainError("Regression target integers cannot safely convert to float64.")
    return []  # Regression has no class vocabulary or positive class.
