"""Target observations only. Never coerce, impute, fit, or choose a task from data."""

import math

from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

from mlstudio.services.source import DomainError, target_classes


def validate_target_for_task(frame, column, task, *, semantic_type=None):
    if task == "binary_classification":
        return target_classes(frame, column)
    if task == "multiclass_classification":
        if column not in frame:
            raise DomainError("Target must belong to the active Dataset.")
        series = frame[column]
        if series.isna().any():
            raise DomainError(
                "Multiclass target labels cannot be missing. Correct the source and upload again."
            )
        values = [v.item() if hasattr(v, "item") else v for v in series.unique()]
        kinds = {type(v) for v in values}
        if len(kinds) != 1 or not kinds.issubset({str, int, bool}):
            raise DomainError(
                "Multiclass labels must be uniformly string, integer or Boolean; "
                "continuous/mixed targets are unsupported."
            )
        if kinds == {int} and semantic_type != "categorical":
            raise DomainError(
                "Review integer target meaning and explicitly mark it categorical in Data; "
                "continuous targets are not classes."
            )
        if not 3 <= len(values) <= 50:
            raise DomainError(
                "Multiclass requires 3–50 distinct classes; multilabel targets are unsupported."
            )
        if any(isinstance(value, str) and len(value) > 1024 for value in values):
            raise DomainError("Multiclass labels must be at most 1,024 characters.")
        from sklearn.utils.multiclass import type_of_target

        try:
            compatible = type_of_target(series) == "multiclass"
        except (TypeError, ValueError, OverflowError):
            compatible = False
        if not compatible:
            raise DomainError(
                "sklearn cannot preserve this multiclass label representation. "
                "Correct the source; labels are never coerced or rounded."
            )
        return sorted(values)
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
