"""Pure current-state reconciliation; no source loading or execution."""

from copy import deepcopy


def empty_pipeline() -> dict:
    return {
        "ir_version": "0.1",
        "dataset": None,
        "target": None,
        "features": {},
        "model": None,
        "split": None,
    }


def initialize(dataset, target: str | None, excluded=()) -> dict:
    ir = empty_pipeline()
    ir["dataset"] = {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint}
    ir["target"] = target_intent(target)
    # Preserve the existing candidate-role default, without inventing preprocessing.
    # Unsupported included semantics are explicit blocking issues, never auto-deleted.
    ir["features"] = {
        c["name"]: {"included": c["name"] not in excluded, "operations": []}
        for c in dataset.columns
        if c["name"] != target
    }
    return ir


def target_intent(column):
    return (
        {"column": column, "positive_class": None, "missing_value_policy": "exclude_rows"}
        if column is not None
        else None
    )


def bound_to(ir, dataset) -> bool:
    return bool(
        ir and ir.get("dataset") == {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint}
    )


def reconcile_target(project, dataset, old_target):
    if not bound_to(project.working_pipeline, dataset):
        return  # A replacement-stale recipe must retain its original context.
    ir = deepcopy(project.working_pipeline)
    if old_target is not None:
        ir["features"][old_target] = {"included": False, "operations": []}
    ir["features"].pop(project.target_column, None)
    ir["target"] = target_intent(project.target_column)
    project.working_pipeline = ir


def column_role(project, dataset, name):
    if name == project.target_column:
        return "target"
    if bound_to(project.working_pipeline, dataset):
        feature = project.working_pipeline["features"].get(name)
        return "feature" if feature and feature["included"] else "excluded"
    # No old-Dataset participation decision is applied to a replacement source.
    return "feature"
