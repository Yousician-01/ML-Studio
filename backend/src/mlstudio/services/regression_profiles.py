"""Read-only numeric target evidence from full source, never a training partition."""

import math

import numpy as np
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_integer_dtype, is_numeric_dtype

from mlstudio.profile_schemas import (
    RegressionProfileResponse,
    RegressionTargetProfile,
    TargetRelationship,
)
from mlstudio.services.pipeline_state import column_role
from mlstudio.services.profiles import COLUMN_LIMIT, effective, numeric_profile
from mlstudio.services.source import DomainError
from mlstudio.services.task_policies import validate_target_for_task

SCATTER_LIMIT = 200


def numeric_feature(series, semantic):
    return (
        is_numeric_dtype(series.dtype)
        and not is_bool_dtype(series.dtype)
        and not is_complex_dtype(series.dtype)
        and semantic in {"continuous", "binary", "unknown"}
    )


def unsafe_integer(series):
    return (
        is_integer_dtype(series.dtype)
        and len(series)
        and any(abs(int(v)) > 2**53 - 1 for v in (series.min(), series.max()))
    )


def pearson(x, y):
    """Centered/scaled Pearson on all complete pairs, no significance claim."""
    if len(x) < 2:
        return None, "Pearson correlation needs at least two complete pairs."
    if np.unique(x).size < 2 or np.unique(y).size < 2:
        return None, "Pearson correlation is unavailable for a constant feature or target."
    centered = []
    with np.errstate(over="ignore", invalid="ignore", divide="ignore", under="ignore"):
        for values in (x, y):
            delta = values - values[0]
            if not np.isfinite(delta).all():
                delta = values / np.max(np.abs(values))
            scale = np.max(np.abs(delta))
            if not math.isfinite(scale) or scale == 0:
                return None, "Variation is below finite correlation precision."
            delta = delta / scale
            centered.append(delta - delta.mean())
        a, b = centered
        denominator = np.sqrt(np.dot(a, a) * np.dot(b, b))
        value = float(np.dot(a, b) / denominator)
    if not math.isfinite(value):
        return None, "Correlation exceeds finite numeric precision."
    return max(-1.0, min(1.0, value)), None


def relationship(frame, feature, target):
    complete = frame[feature].notna() & frame[target].notna()
    left, right = frame.loc[complete, feature], frame.loc[complete, target]
    count = len(left)
    reason = None
    points = []
    correlation, correlation_reason = None, None
    if unsafe_integer(left) or unsafe_integer(right):
        reason = "Source integers exceed safe chart/correlation precision."
        correlation_reason = reason
    else:
        x, y = left.to_numpy(dtype=float), right.to_numpy(dtype=float)
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            reason = "Source pairs contain non-finite values."
            correlation_reason = reason
        else:
            correlation, correlation_reason = pearson(x, y)
            if count:
                # Keep SVG coordinate spans finite too, not only individual values.
                with np.errstate(over="ignore", invalid="ignore"):
                    spans = [float(v.max() - v.min()) for v in (x, y)]
                if not all(math.isfinite(span) for span in spans):
                    reason = "Numeric range exceeds finite chart precision."
                else:
                    indices = np.linspace(0, count - 1, min(count, SCATTER_LIMIT), dtype=int)
                    points = [dict(x=float(x[i]), y=float(y[i])) for i in indices]
            else:
                reason = "No complete source pairs are available."
    return TargetRelationship(
        feature=feature,
        target=target,
        paired_rows=count,
        missing_pair_rows=len(frame) - count,
        missing_feature_rows=int(frame[feature].isna().sum()),
        missing_target_rows=int(frame[target].isna().sum()),
        pearson=correlation,
        correlation_unavailable_reason=correlation_reason,
        points=points,
        scatter_unavailable_reason=reason,
    )


def build_regression_profile(frame, dataset, project, offset=0, feature=None):
    target_name = project.target_column
    target = None
    if target_name is not None:
        validate_target_for_task(frame, target_name, "regression")
        column = next(c for c in dataset.columns if c["name"] == target_name)
        series = frame[target_name]
        target = RegressionTargetProfile(
            name=target_name,
            physical_dtype=str(series.dtype),
            semantic_type=effective(column),
            role="target",
            observed_count=int(series.count()),
            missing_count=int(series.isna().sum()),
            distinct_count=int(series.nunique()),
            constant=series.nunique() == 1,
            numeric=numeric_profile(series),
        )
    candidates = [
        c
        for c in sorted(dataset.columns, key=lambda c: c["source_order"])
        if c["name"] != target_name and numeric_feature(frame[c["name"]], effective(c))
    ]
    if feature is not None and feature not in {c["name"] for c in candidates}:
        raise DomainError("Choose an available numeric source feature.", 422)
    page = candidates[offset : offset + COLUMN_LIMIT]
    selected = feature if feature is not None else (page[0]["name"] if page else None)
    return RegressionProfileResponse(
        dataset_id=dataset.id,
        revision=project.revision,
        fingerprint=dataset.fingerprint,
        original_filename=dataset.original_filename,
        row_count=len(frame),
        column_count=len(frame.columns),
        target=target,
        numeric_feature_count=len(candidates),
        feature_offset=offset,
        feature_options=[
            dict(
                name=c["name"],
                physical_dtype=c["physical_dtype"],
                semantic_type=effective(c),
                role=column_role(project, dataset, c["name"]),
            )
            for c in page
        ],
        relationship=relationship(frame, selected, target_name) if selected and target else None,
    )
