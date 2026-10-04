"""Read-only library compatibility checks. No estimator fitting or feature splitting."""

import platform
from importlib.metadata import version

import pandas as pd
from sklearn.utils.multiclass import type_of_target

from mlstudio.codegen.csv_runtime import lossy_nullable_integers
from mlstudio.pipeline_schemas import PipelineIssue


def library_versions():
    return {name: version(name) for name in ("pandas", "numpy", "scikit-learn", "joblib", "scipy")}


def python_version():
    return platform.python_version()


def target_supported(series):
    """No coercion: sklearn must recognize the exact parsed non-missing labels."""
    try:
        return not lossy_nullable_integers(series) and type_of_target(series.dropna()) == "binary"
    except (TypeError, ValueError, OverflowError):
        return False


def compatibility_issues(ir, dataset, frame):
    issues = []
    if dataset is None:
        return issues
    # Fixture-only lightweight objects used by the domain validator need no provenance.
    if getattr(dataset, "parsing_version", "csv-utf8-v1") != "csv-utf8-v1" or (
        getattr(dataset, "pandas_version", pd.__version__) != pd.__version__
    ):
        issues.append(
            PipelineIssue(
                scope="train",
                code="parser_context",
                message="Source parser/version differs from ingestion. Restore its supported "
                "environment or upload a new Dataset and review the configuration.",
            )
        )
    versions = library_versions()
    if versions["scikit-learn"] != "1.9.1" or not versions["joblib"].startswith("1.5."):
        issues.append(
            PipelineIssue(
                scope="train",
                code="library_context",
                message="Restore the documented sklearn/joblib environment before generating code.",
            )
        )
    if ir.target and ir.target.column in frame:
        target = frame[ir.target.column]
        if target.nunique() == 2 and not target_supported(target):
            issues.append(
                PipelineIssue(
                    scope="train",
                    column=ir.target.column,
                    code="target_representation",
                    message="This target representation is unsupported by sklearn classifiers. "
                    "Choose a compatible target or correct the source and upload a new Dataset; "
                    "Labels are never rounded, stringified, or encoded automatically.",
                )
            )
    columns = {c["name"]: c for c in dataset.columns}
    for name, feature in ir.features.items():
        if not feature.included or name not in frame or name not in columns:
            continue
        column = columns[name]
        semantic = column["semantic_override"] or column["inferred_semantic_type"]
        if semantic in {"categorical", "binary"} and lossy_nullable_integers(frame[name]):
            issues.append(
                PipelineIssue(
                    scope="feature",
                    column=name,
                    code="feature_representation",
                    message="sklearn cannot preserve these nullable large integer categories. "
                    "Exclude this feature or correct the source and upload a new Dataset; "
                    "values are never rounded or recoded automatically.",
                )
            )
    return issues
