"""Admission and configuration-only diagnostics; never fit exploratory populations."""

from types import SimpleNamespace

import numpy as np
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from mlstudio.outlier_schemas import ResolvedOutlierConfig


def context(ir, dataset, frame):
    if ir.outlier_treatment is None:
        return dataset, frame, {}
    columns, expanded, diagnostics = list(dataset.columns), frame.copy(), {}
    existing = {c["name"]: c for c in dataset.columns}
    reserved_indicators = {
        config.indicator
        for config in (ir.imputation.columns.values() if ir.imputation else [])
        if config.indicator
    }
    produced = set()
    for feature in ir.outlier_treatment.features:
        column = existing.get(feature.source)
        if (
            not column
            or feature.source == (ir.target.column if ir.target else None)
            or column.get("inference_version") in {"imputation-v1", "outlier-treatment-v1"}
        ):
            raise ValueError(
                "Outlier input must be an existing non-target source, temporal, generalized "
                "or numeric engineered feature; outlier chaining is unsupported."
            )
        if (
            (column["semantic_override"] or column["inferred_semantic_type"]) != "continuous"
            or not is_numeric_dtype(frame[feature.source].dtype)
            or is_bool_dtype(frame[feature.source].dtype)
        ):
            raise ValueError("Outlier treatment requires continuous numeric semantics.")
        for name, semantic in [(feature.name, "continuous"), (feature.indicator, "binary")]:
            if not name:
                continue
            if name in existing or name in produced or name in reserved_indicators:
                raise ValueError(
                    "Outlier output or indicator name collides with an existing column."
                )
            if ir.imputation and name in ir.imputation.columns:
                raise ValueError(
                    "Outlier outputs cannot feed the earlier Advanced Imputation stage; "
                    "use branch imputation."
                )
            produced.add(name)
            upstream = ir.imputation and feature.source in ir.imputation.columns
            expanded[name] = (
                0.0 if upstream else np.where(frame[feature.source].notna(), 0.0, np.nan)
            )
            columns.append(
                {
                    "name": name,
                    "source_order": len(columns),
                    "physical_dtype": "float64",
                    "missing_count": column["missing_count"],
                    "unique_count": 0,
                    "inferred_semantic_type": semantic,
                    "semantic_override": None,
                    "inference_version": "outlier-treatment-v1",
                }
            )
        diagnostics[feature.name] = {
            "fitted": True,
            "missing_count": column["missing_count"],
            "multiplier": feature.multiplier,
            "message": "Configuration only. IQR fences and indicator thresholds fit training rows "
            "exclusively; exploratory source fences are not reused.",
        }
    virtual = SimpleNamespace(
        **{
            key: getattr(dataset, key)
            for key in ("id", "fingerprint", "size_bytes", "parsing_version", "pandas_version")
            if hasattr(dataset, key)
        },
        columns=columns,
    )
    return virtual, expanded, diagnostics


def validate_selection(ir, dataset, frame):
    if ir.feature_selection is None:
        return
    columns = {c["name"]: c for c in dataset.columns}
    for name in ir.feature_selection.features:
        column, intent = columns.get(name), ir.features.get(name)
        if (
            name == (ir.target.column if ir.target else None)
            or not column
            or not intent
            or not intent.included
        ):
            raise ValueError(
                "Variance eligibility must reference included non-target features. "
                "Remove excluded or deleted features from selection eligibility."
            )
        if (
            (column["semantic_override"] or column["inferred_semantic_type"]) != "continuous"
            or not is_numeric_dtype(frame[name].dtype)
            or is_bool_dtype(frame[name].dtype)
            or any(op.type == "encode" for op in intent.operations)
        ):
            raise ValueError(
                "Variance selection supports continuous numeric scalar branches only, "
                "never encoded categories or arbitrary numeric category codes."
            )


def resolved(ir, dataset, frame):
    if ir.outlier_treatment is None:
        return None
    return ResolvedOutlierConfig(
        **ir.outlier_treatment.model_dump(mode="json"),
        input_dtypes={
            f.source: str(frame[f.source].dtype)
            for f in ir.outlier_treatment.features
            if f.source in frame
        },
    )
