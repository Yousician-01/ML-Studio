"""Bounded deterministic source EDA. No fitted state, recommendations, or IR."""

import math
from collections import Counter

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_integer_dtype, is_numeric_dtype
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlstudio.core.config import Settings
from mlstudio.models import Dataset, Project
from mlstudio.profile_schemas import (
    ColumnProfile,
    CorrelationProfile,
    Frequency,
    NumericProfile,
    ProfileResponse,
    TargetProfile,
)
from mlstudio.services.artifacts import verified_source
from mlstudio.services.pipeline_state import column_role
from mlstudio.services.source import DomainError, json_scalar, parse_source

COLUMN_LIMIT = 20
CATEGORY_LIMIT = 10
HISTOGRAM_BINS = 10
CORRELATION_LIMIT = 12


def percentage(count: int, total: int) -> float:
    return 100 * count / total if total else 0.0


def frequencies(
    series: pd.Series, limit: int, truncate: bool = True
) -> tuple[list[Frequency], int]:
    # Stable sort preserves first source occurrence for equal counts.
    counts = series.dropna().value_counts(sort=False).sort_values(ascending=False, kind="stable")
    total = int(counts.sum())
    result = []
    for value, count in counts.iloc[:limit].items():
        value = json_scalar(value)
        shortened = truncate and isinstance(value, str) and len(value) > 120
        result.append(
            Frequency(
                value=value[:120] if shortened else value,
                count=int(count),
                percentage=percentage(int(count), total),
                label_truncated=shortened,
            )
        )
    return result, total - sum(item.count for item in result)


def numeric_profile(series: pd.Series) -> NumericProfile:
    observed = series.dropna()
    base = dict(
        count=len(observed),
        mean=None,
        standard_deviation=None,
        minimum=None,
        q1=None,
        median=None,
        q3=None,
        maximum=None,
        lower_whisker=None,
        upper_whisker=None,
        outlier_count=0,
        histogram=[],
    )
    if observed.empty:
        return NumericProfile(**base, unavailable_reason="No non-missing numeric values.")
    base.update(minimum=json_scalar(observed.min()), maximum=json_scalar(observed.max()))
    # Exact scalar extrema remain inspectable; do not draw rounded/merged integer bins.
    if is_integer_dtype(observed.dtype) and any(
        abs(int(v)) > 2**53 - 1 for v in (observed.min(), observed.max())
    ):
        return NumericProfile(
            **base,
            unavailable_reason="Exact integer extrema are shown; floating-point summaries "
            "and charts "
            "are unavailable beyond the safe integer range.",
        )
    values = observed.to_numpy(dtype=float)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75], method="linear")
        mean = float(np.mean(values))
        std = float(np.std(values, ddof=1)) if len(values) > 1 else None
        lo, hi = float(values.min()), float(values.max())
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        if not all(
            math.isfinite(v)
            for v in [q1, median, q3, mean, lo, hi, hi - lo, lower, upper, std or 0]
        ):
            return NumericProfile(
                **base, unavailable_reason="Numeric range exceeds finite summary precision."
            )
        inside = values[(values >= lower) & (values <= upper)]
        if lo == hi:
            histogram = [dict(lower=lo, upper=hi, count=len(values))]
        else:
            # Adjacent floats cannot support ten distinct edges. Collapse repeated
            # edges explicitly, retaining every observation rather than failing EDA.
            edges = np.unique(np.linspace(lo, hi, HISTOGRAM_BINS + 1))
            counts, edges = np.histogram(values, bins=edges)
            histogram = [
                dict(lower=float(edges[i]), upper=float(edges[i + 1]), count=int(count))
                for i, count in enumerate(counts)
            ]
    return NumericProfile(
        **{
            **base,
            "mean": mean,
            "standard_deviation": std,
            "q1": float(q1),
            "median": float(median),
            "q3": float(q3),
            # Interpolated quartiles may lie beyond the last in-fence sample in
            # small/skewed data. Whiskers must never point inward across the box.
            "lower_whisker": float(min(q1, inside.min())),
            "upper_whisker": float(max(q3, inside.max())),
            "outlier_count": len(values) - len(inside),
            "histogram": histogram,
        }
    )


def effective(column: dict) -> str:
    return column["semantic_override"] or column["inferred_semantic_type"]


def numeric_applicable(series: pd.Series, semantic: str) -> bool:
    return (
        is_numeric_dtype(series.dtype)
        and not is_bool_dtype(series.dtype)
        and semantic in {"continuous", "unknown"}
    )


def correlations(frame: pd.DataFrame, dataset: Dataset, project: Project) -> CorrelationProfile:
    # Features only: no arbitrary numerical encoding/order for binary target labels.
    eligible = [
        c["name"]
        for c in dataset.columns
        if c["name"] != project.target_column
        and column_role(project, dataset, c["name"]) == "feature"
        and effective(c) == "continuous"
        and numeric_applicable(frame[c["name"]], effective(c))
    ]
    names = eligible[:CORRELATION_LIMIT]
    values = [[None for _ in names] for _ in names]
    counts = [[0 for _ in names] for _ in names]
    for i, left in enumerate(names):
        for j in range(i, len(names)):
            right = names[j]
            pair = frame[[left, right]].dropna()
            counts[i][j] = counts[j][i] = len(pair)
            a, b = pair.iloc[:, 0], pair.iloc[:, 1]
            unsafe = (
                any(
                    is_integer_dtype(s.dtype)
                    and any(abs(int(v)) > 2**53 - 1 for v in (s.min(), s.max()))
                    for s in (a, b)
                )
                if len(pair)
                else False
            )
            if len(pair) < 2 or a.nunique() < 2 or b.nunique() < 2 or unsafe:
                continue
            # Positive scaling prevents overflow without changing Pearson correlation.
            x, y = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
            x, y = x / np.max(np.abs(x)), y / np.max(np.abs(y))
            with np.errstate(invalid="ignore", divide="ignore"):
                value = float(np.corrcoef(x, y)[0, 1])
            if math.isfinite(value):
                values[i][j] = values[j][i] = max(-1.0, min(1.0, value))
    return CorrelationProfile(
        columns=names,
        values=values,
        pair_counts=counts,
        eligible_count=len(eligible),
        column_limit=CORRELATION_LIMIT,
        unavailable_reason="At least two continuous numeric features are needed."
        if len(names) < 2
        else None,
    )


def build_profile(
    frame: pd.DataFrame, dataset: Dataset, project: Project, offset: int
) -> ProfileResponse:
    rows = len(frame)
    columns = []
    for column in dataset.columns[offset : offset + COLUMN_LIMIT]:
        name, semantic = column["name"], effective(column)
        series = frame[name]
        count, unique, missing = (
            int(series.count()),
            int(series.nunique()),
            int(series.isna().sum()),
        )
        numeric = numeric_profile(series) if numeric_applicable(series, semantic) else None
        freq, other = (
            frequencies(series, CATEGORY_LIMIT)
            if semantic in {"categorical", "binary"}
            else (None, 0)
        )
        reason = (
            None
            if numeric or freq
            else "No distribution for this semantic/physical type. "
            "Source observations remain available."
        )
        if count == 0:
            reason = "All values are missing."
        columns.append(
            ColumnProfile(
                name=name,
                physical_dtype=column["physical_dtype"],
                semantic_type=semantic,
                role=column_role(project, dataset, name),
                non_missing_count=count,
                missing_count=missing,
                missing_percentage=percentage(missing, rows),
                distinct_count=unique,
                uniqueness_percentage=percentage(unique, count),
                high_cardinality=semantic in {"categorical", "binary", "text", "identifier"}
                and unique >= 20
                and unique / max(count, 1) >= 0.5,
                identifier=semantic == "identifier",
                numeric=numeric,
                frequencies=freq,
                other_count=other,
                unavailable_reason=reason,
            )
        )
    target = None
    if project.target_column:
        series = frame[project.target_column]
        classes, _ = frequencies(series, 2, truncate=False)
        if series.nunique() != 2:
            raise DomainError(
                "The current target no longer has exactly two classes. Reload Data.", 409
            )
        target = TargetProfile(
            column=project.target_column,
            missing_count=int(series.isna().sum()),
            non_missing_count=int(series.count()),
            classes=classes,
            majority_percentage=max(item.percentage for item in classes),
        )
    return ProfileResponse(
        dataset_id=dataset.id,
        revision=project.revision,
        fingerprint=dataset.fingerprint,
        original_filename=dataset.original_filename,
        row_count=rows,
        column_count=len(frame.columns),
        feature_count=sum(
            c["name"] != project.target_column
            and column_role(project, dataset, c["name"]) == "feature"
            for c in dataset.columns
        ),
        missing_cells=dataset.missing_cells,
        missing_percentage=percentage(dataset.missing_cells, rows * len(frame.columns)),
        duplicate_rows=dataset.duplicate_rows,
        duplicate_percentage=percentage(dataset.duplicate_rows, rows),
        semantic_counts=dict(Counter(effective(c) for c in dataset.columns)),
        target=target,
        columns=columns,
        column_offset=offset,
        column_limit=COLUMN_LIMIT,
        category_limit=CATEGORY_LIMIT,
        histogram_bin_limit=HISTOGRAM_BINS,
        correlation=correlations(frame, dataset, project),
    )


def read_profile(
    session: Session,
    project_id: str,
    dataset_id: str,
    revision: int,
    offset: int,
    settings: Settings,
) -> ProfileResponse:
    snapshot = session.execute(
        select(Project, Dataset)
        .join(Dataset, Dataset.id == Project.active_dataset_id)
        .where(Project.id == project_id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if snapshot is None:
        raise DomainError("No active Dataset is available. Return to Data.", 404)
    project, dataset = snapshot
    if dataset.id != dataset_id or project.revision != revision:
        raise DomainError(
            "Dataset or configuration changed. Reload the workspace to Explore its current source.",
            409,
        )
    frame = parse_source(verified_source(settings.home, dataset))
    result = build_profile(frame, dataset, project, offset)
    # A concurrent replacement during computation cannot be presented as current.
    latest = session.execute(
        select(Project.active_dataset_id, Project.revision).where(Project.id == project_id)
    ).one_or_none()
    if latest is None or latest != (dataset.id, revision):
        raise DomainError("Dataset changed during profiling. Reload the workspace.", 409)
    return result
