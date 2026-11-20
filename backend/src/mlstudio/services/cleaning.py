"""Source-bound stateless cleaning and training-only selection, never fitting."""

from types import SimpleNamespace

from mlstudio.cleaning_runtime_v1 import cleaning_select, cleaning_transform, cleaning_validate
from mlstudio.cleaning_schemas import ResolvedCleaningConfig


def virtual(dataset, columns):
    return SimpleNamespace(
        **{
            key: getattr(dataset, key)
            for key in ("id", "fingerprint", "size_bytes", "parsing_version", "pandas_version")
            if hasattr(dataset, key)
        },
        columns=columns,
    )


def types(dataset, frame):
    from mlstudio.cleaning_runtime_v1 import cleaning_types

    result = cleaning_types(frame)
    for column in dataset.columns:
        semantic = column["semantic_override"] or column["inferred_semantic_type"]
        if semantic == "datetime":
            result[column["name"]] = "datetime"
        elif (
            column.get("inference_version") in {"derived-v1", "temporal-v1"}
            and semantic == "binary"
        ):
            result[column["name"]] = "boolean"
    return result


def raw_context(ir, dataset, frame, *, diagnostic=False):
    if ir.cleaning is None:
        return dataset, frame, []
    config = {
        **ir.cleaning.model_dump(mode="json"),
        "input_types": types(dataset, frame),
        "target": ir.target.column if ir.target else None,
    }
    expanded, diagnostics = cleaning_transform(frame, config, diagnostic=diagnostic)
    semantics = {}
    for step in ir.cleaning.steps:
        if step.kind == "convert":
            semantics[step.column] = step.destination
        elif step.kind == "datetime_fill":
            semantics[step.column] = "datetime"
    columns = [
        {
            **column,
            "physical_dtype": str(expanded[column["name"]].dtype),
            "missing_count": int(expanded[column["name"]].isna().sum()),
            "unique_count": int(expanded[column["name"]].nunique()),
            "semantic_override": semantics.get(column["name"], column["semantic_override"]),
            "inference_version": "cleaning-v1"
            if column["name"] in semantics
            else column.get("inference_version", "semantic-v1"),
        }
        for column in dataset.columns
    ]
    return virtual(dataset, columns), expanded, diagnostics


def temporal_config(ir):
    """Canonical cleaned timestamps require ISO parsing at the next fixed stage."""
    if ir.temporal is None:
        return None
    result = ir.temporal.model_copy(deep=True)
    for step in ir.cleaning.steps if ir.cleaning else []:
        if (
            step.kind == "datetime_fill"
            or step.kind == "convert"
            and step.destination == "datetime"
        ) and step.column in result.sources:
            result.sources[step.column] = result.sources[step.column].model_copy(
                update={"format": "ISO8601", "naive": "reject"}
            )
    return result


def selection(ir, raw_dataset, raw_frame, dataset, expanded, *, validate_targets=True):
    if ir.cleaning is None:
        return expanded, []
    config = {
        **ir.cleaning.model_dump(mode="json"),
        "input_types": types(dataset, expanded),
        "target": ir.target.column if ir.target else None,
    }
    cleaning_validate(
        config, types(raw_dataset, raw_frame), config["target"], types(dataset, expanded)
    )
    selected, events = cleaning_select(expanded, config)
    target = config["target"]
    if validate_targets and target and target in raw_frame:
        if ir.ir_version == "0.3" and raw_frame[target].isna().any():
            raise ValueError(
                "Multiclass target cannot contain missing labels, even before selection."
            )
        if ir.ir_version in {"0.1", "0.3"}:
            if set(raw_frame[target].dropna().unique()) != set(selected[target].dropna().unique()):
                raise ValueError(
                    "Row selection removed a target class. Adjust the filters or duplicate keys."
                )
    return selected, events


def population(ir, dataset, frame):
    if ir.cleaning is None:
        return {"source": len(frame), "eligible": int(frame[ir.target.column].count())}
    from mlstudio.services.derived import context

    virtual_dataset, expanded, _, errors = context(ir, dataset, frame)
    if errors:
        raise ValueError("Cleaned temporal inputs are invalid.")
    selected, _ = selection(ir, dataset, frame, virtual_dataset, expanded)
    return {"source": len(frame), "eligible": int(selected[ir.target.column].count())}


def resolved(ir, dataset, frame):
    if ir.cleaning is None:
        return None
    from mlstudio.services.derived import context

    expanded_dataset, expanded, _, _ = context(ir, dataset, frame)
    return ResolvedCleaningConfig(
        **ir.cleaning.model_dump(mode="json"),
        selection_types=types(expanded_dataset, expanded),
        input_types=types(dataset, frame),
        input_dtypes={
            column["name"]: str(frame[column["name"]].dtype) for column in dataset.columns
        },
        target=ir.target.column if ir.target else None,
    )


def evidence(dataset, selected, source_count, events, diagnostics):
    from mlstudio.services.source import json_scalar

    names = [column["name"] for column in dataset.columns]
    return {
        "columns": [
            {
                "name": c["name"],
                "physical_dtype": str(selected[c["name"]].dtype),
                "semantic_type": c["semantic_override"] or c["inferred_semantic_type"],
                "missing_count": int(selected[c["name"]].isna().sum()),
                "unique_count": int(selected[c["name"]].nunique()),
            }
            for c in dataset.columns
        ],
        "rows": [
            [json_scalar(value) for value in row]
            for row in selected[names].head(20).itertuples(index=False, name=None)
        ],
        "row_indices": [int(index) for index in selected.head(20).index],
        "source_rows": source_count,
        "retained_rows": len(selected),
        "removed_rows": source_count - len(selected),
        "events": events,
        "diagnostics": [
            {**d, "examples": [json_scalar(value) for value in d.get("examples", [])]}
            for d in diagnostics
        ],
    }
