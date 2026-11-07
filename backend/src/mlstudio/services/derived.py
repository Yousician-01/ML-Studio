"""Compose stateless feature stages without changing the managed Dataset."""

from types import SimpleNamespace

import numpy as np
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from mlstudio.derived_runtime_v1 import derived_transform
from mlstudio.derived_schemas import ResolvedDerivedConfig, validate_derived


def source_types(dataset, frame):
    result = {}
    for column in dataset.columns:
        name = column["name"]
        semantic = column["semantic_override"] or column["inferred_semantic_type"]
        series = frame[name]
        observed = series.dropna()
        kind = "unsupported"
        if semantic != "datetime":
            if is_bool_dtype(series.dtype) or (
                len(observed)
                and observed.map(lambda value: isinstance(value, (bool, np.bool_))).all()
            ):
                kind = "boolean"
            elif is_numeric_dtype(series.dtype) and semantic in {
                "continuous",
                "binary",
                "categorical",
            }:
                kind = "numeric"
            elif (
                not is_numeric_dtype(series.dtype)
                and series.dropna().map(lambda value: isinstance(value, str)).all()
            ):
                kind = "string"
        result[name] = kind
    return result


def context(ir, dataset, frame):
    """Temporal outputs may feed derived-v1, never the reverse direction."""
    from mlstudio.services.temporal import context as temporal_context

    raw_dataset = dataset
    counts, errors = {}, []
    if ir.temporal is not None:
        dataset, frame, counts, errors = temporal_context(ir, dataset, frame)
    if ir.derived is None:
        return dataset, frame, counts, errors
    types = source_types(raw_dataset, frame)
    temporal_types = {
        column["name"]: "boolean" if column["inferred_semantic_type"] == "binary" else "numeric"
        for column in dataset.columns[len(raw_dataset.columns) :]
    }
    _, outputs = validate_derived(
        ir.derived, types, ir.target.column if ir.target else None, temporal_types
    )
    config = {
        **ir.derived.model_dump(mode="json"),
        "input_types": {**types, **temporal_types},
        "output_types": outputs,
    }
    expanded, diagnostics = derived_transform(frame, config)
    columns = list(dataset.columns)
    for feature in ir.derived.features:
        name = feature.name
        series = expanded[name]
        columns.append(
            {
                "name": name,
                "source_order": len(columns),
                "physical_dtype": str(series.dtype),
                "missing_count": int(series.isna().sum()),
                "unique_count": int(series.nunique()),
                "inferred_semantic_type": {
                    "numeric": "continuous",
                    "boolean": "binary",
                    "string": "categorical",
                }[outputs[name]],
                "semantic_override": None,
                "inference_version": "derived-v1",
            }
        )
    virtual = SimpleNamespace(
        **{
            key: getattr(dataset, key)
            for key in ("id", "fingerprint", "size_bytes", "parsing_version", "pandas_version")
            if hasattr(dataset, key)
        },
        columns=columns,
        derived_diagnostics=diagnostics,
    )
    return virtual, expanded, counts, errors


def resolved(ir, dataset, frame):
    if ir.derived is None:
        return None
    types = source_types(dataset, frame)
    temporal_types = {}
    if ir.temporal is not None:
        from mlstudio.temporal_schemas import validate_temporal

        _, observed = validate_temporal(
            ir.temporal,
            {
                c["name"]: c["semantic_override"] or c["inferred_semantic_type"]
                for c in dataset.columns
            },
            ir.target.column if ir.target else None,
        )
        temporal_types = {
            name: "boolean" if kind[0] == "binary" else "numeric" for name, kind in observed.items()
        }
    _, outputs = validate_derived(
        ir.derived, types, ir.target.column if ir.target else None, temporal_types
    )

    def columns(expression):
        if expression.kind == "column":
            return [expression.name]
        if expression.kind == "call":
            return [name for argument in expression.arguments for name in columns(argument)]
        return []

    inputs = dict.fromkeys(
        name for feature in ir.derived.features for name in columns(feature.expression)
    )
    return ResolvedDerivedConfig(
        **ir.derived.model_dump(mode="json"),
        input_types={**types, **temporal_types},
        output_types=outputs,
        input_dtypes={name: str(frame[name].dtype) for name in inputs},
    )
