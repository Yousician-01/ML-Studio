"""Configuration-only evidence for train-fitted imputation; never fits source data."""

from types import SimpleNamespace

from mlstudio.imputation_runtime_v1 import imputation_diagnostics, validate_imputation
from mlstudio.imputation_schemas import ResolvedImputationConfig
from mlstudio.services.derived import source_types


def active_columns(ir):
    return {
        name: config
        for name, config in (ir.imputation.columns.items() if ir.imputation else [])
        if ir.features.get(name)
        and (
            ir.features[name].included
            or any(
                f.source == name
                for f in (ir.feature_engineering.features if ir.feature_engineering else [])
            )
        )
    }


def input_types(dataset, frame):
    types = source_types(dataset, frame)
    for column in dataset.columns:
        if column.get("inference_version") in {"derived-v1", "temporal-v1"}:
            if column["inferred_semantic_type"] == "binary":
                types[column["name"]] = "boolean"
    return types


def context(ir, dataset, frame):
    if ir.imputation is None:
        return dataset, frame, {}
    types = input_types(dataset, frame)
    config = ir.imputation.model_dump(mode="json")
    validate_imputation(config, types, ir.target.column if ir.target else None)
    for name in ir.imputation.columns:
        column = next(c for c in dataset.columns if c["name"] == name)
        if (column["semantic_override"] or column["inferred_semantic_type"]) not in {
            "continuous",
            "categorical",
            "binary",
        }:
            raise ValueError("Advanced imputation requires a supported model feature type.")
        if name not in ir.features:
            raise ValueError("Advanced imputation requires an existing feature configuration.")
        if any(op.type == "impute" for op in ir.features[name].operations):
            raise ValueError("Remove the quick imputer before applying advanced imputation.")
    config["input_types"] = types
    diagnostics = imputation_diagnostics(frame, config)
    columns, expanded = list(dataset.columns), frame.copy()
    for name, settings in active_columns(ir).items():
        if settings.indicator:
            indicator = settings.indicator
            expanded[indicator] = frame[name].isna().astype(float)
            columns.append(
                {
                    "name": indicator,
                    "source_order": len(columns),
                    "physical_dtype": "float64",
                    "missing_count": 0,
                    "unique_count": int(expanded[indicator].nunique()),
                    "inferred_semantic_type": "binary",
                    "semantic_override": None,
                    "inference_version": "imputation-v1",
                }
            )
    virtual = SimpleNamespace(
        **{
            key: getattr(dataset, key)
            for key in ("id", "fingerprint", "size_bytes", "parsing_version", "pandas_version")
            if hasattr(dataset, key)
        },
        columns=columns,
    )
    return virtual, expanded, diagnostics


def resolved(ir, dataset, frame):
    if not active_columns(ir):
        return None
    from mlstudio.services.derived import context as rowwise_context

    raw = frame
    virtual, expanded, _, _ = rowwise_context(ir, dataset, frame)
    context(ir, virtual, expanded)  # Shared contextual admission; no fit/statistics.
    types = input_types(virtual, expanded)
    config = {
        "version": "imputation-v1",
        "columns": {
            name: settings.model_dump(mode="json") for name, settings in active_columns(ir).items()
        },
    }

    def references(expression):
        if expression is None:
            return []
        if expression.kind in {"column", "reference"}:
            return [expression.name]
        if expression.kind == "call":
            return [name for argument in expression.arguments for name in references(argument)]
        return []

    needed = set(config["columns"])
    for settings in active_columns(ir).values():
        for rule in settings.rules:
            needed.update(rule.group_by)
            needed.update(references(rule.condition))
    return ResolvedImputationConfig(
        **config,
        input_types=types,
        input_dtypes={name: str(raw[name].dtype) for name in sorted(needed) if name in raw},
    )
