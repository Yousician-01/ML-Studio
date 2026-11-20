"""Virtual engineering outputs and configuration-only admission for fitted stages."""

from types import SimpleNamespace

import numpy as np

from mlstudio.feature_engineering_runtime_v1 import (
    engineering_fitted,
    engineering_preview,
    engineering_semantic,
    engineering_validate,
)
from mlstudio.feature_engineering_schemas import ResolvedEngineeringConfig
from mlstudio.services.imputation import input_types


def upstream_imputation(ir, name, diagnostics):
    """Follow only admitted engineering edges; introduced nulls are not upstream fills."""
    definitions = {
        f.name: f for f in (ir.feature_engineering.features if ir.feature_engineering else [])
    }
    seen = set()
    while name not in seen:
        seen.add(name)
        if ir.imputation and name in ir.imputation.columns:
            return ir.imputation.columns[name]
        if name not in definitions or diagnostics.get(name, {}).get("invalid_count", 0):
            return None
        name = definitions[name].source
    return None


def context(ir, dataset, frame):
    if ir.feature_engineering is None:
        return dataset, frame, {}
    config = ir.feature_engineering.model_dump(mode="json")
    types = input_types(dataset, frame)
    # Indicators belong to a post-imputation stage, not the raw/derived contract.
    types = {
        name: kind
        for name, kind in types.items()
        if not any(
            c["name"] == name and c.get("inference_version") == "imputation-v1"
            for c in dataset.columns
        )
    }
    engineering_validate(config, types, ir.target.column if ir.target else None)
    semantics = {
        c["name"]: c["semantic_override"] or c["inferred_semantic_type"] for c in dataset.columns
    }
    for feature in config["features"]:
        if feature["name"] in frame.columns:
            raise ValueError("Engineering output collides with an existing feature or indicator.")
        if feature["method"] in {"rare", "ordinal"} and semantics[feature["source"]] not in {
            "categorical",
            "binary",
        }:
            raise ValueError("Category transformations require categorical or binary semantics.")
        if (
            feature["method"] not in {"rare", "ordinal"}
            and semantics[feature["source"]] != "continuous"
        ):
            raise ValueError("Numeric transformations require continuous semantics.")
        semantics[feature["name"]] = engineering_semantic(feature)
        if ir.imputation and feature["name"] in ir.imputation.columns:
            raise ValueError(
                "Engineering outputs cannot feed the earlier advanced imputation stage. "
                "Use an output branch imputer."
            )
    expanded, diagnostics = engineering_preview(frame, config)
    columns = list(dataset.columns)
    for feature in config["features"]:
        name = feature["name"]
        semantic = engineering_semantic(feature)
        if engineering_fitted(feature):
            # Placeholder types for validation only. Never expose these as preview values.
            expanded[name] = "unfitted" if semantic == "categorical" else 0.0
            # Preserve observable missingness for admission, unless the input has
            # an earlier advanced imputer whose actual fit/transform verifies fills.
            upstream = upstream_imputation(ir, feature["source"], diagnostics)
            if not upstream:
                expanded[name] = expanded[name].where(expanded[feature["source"]].notna(), np.nan)
        columns.append(
            {
                "name": name,
                "source_order": len(columns),
                "physical_dtype": "object" if semantic == "categorical" else "float64",
                "missing_count": diagnostics[name]["missing_count"],
                "unique_count": 0 if engineering_fitted(feature) else int(expanded[name].nunique()),
                "inferred_semantic_type": semantic,
                "semantic_override": None,
                "inference_version": "feature-engineering-v1",
            }
        )
    return (
        SimpleNamespace(
            **{
                key: getattr(dataset, key)
                for key in ("id", "fingerprint", "size_bytes", "parsing_version", "pandas_version")
                if hasattr(dataset, key)
            },
            columns=columns,
            engineering_diagnostics=diagnostics,
        ),
        expanded,
        diagnostics,
    )


def resolved(ir, dataset, frame):
    if ir.feature_engineering is None:
        return None
    from mlstudio.services.derived import context as rowwise_context

    virtual, expanded, _, _ = rowwise_context(ir, dataset, frame)
    if ir.cleaning is not None:
        from mlstudio.services.cleaning import selection

        expanded, _ = selection(ir, dataset, frame, virtual, expanded)
    context(ir, virtual, expanded)
    return ResolvedEngineeringConfig(
        **ir.feature_engineering.model_dump(mode="json"),
        input_types=input_types(virtual, expanded),
        input_dtypes={
            f.source: str(frame[f.source].dtype)
            for f in ir.feature_engineering.features
            if f.source in frame
        },
    )
