"""Standalone row-wise cleaning plus explicit training-only Dataset selection."""

import ast
import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.cleaning is None:
        return source
    config = plan.cleaning.model_dump(mode="json")
    selection_kinds = {"filter", "missing_filter", "deduplicate"}
    row_config = {
        **config,
        "steps": [s for s in config["steps"] if s["kind"] not in selection_kinds],
    }
    parsed = ast.parse(source)
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in parsed.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"FEATURES", "PHYSICAL_DTYPES"}
    }
    if set(constants) != {"FEATURES", "PHYSICAL_DTYPES"}:
        raise ValueError("Cleaning source constants are unavailable.")

    def inputs(expression):
        if not expression:
            return []
        if expression["kind"] in {"column", "reference"}:
            return [expression["name"]]
        return [name for arg in expression.get("arguments", []) for name in inputs(arg)]

    required = list(constants["FEATURES"])
    for step in row_config["steps"]:
        required.append(step["column"])
        required.extend(inputs(step.get("condition")))
    required = list(dict.fromkeys(required))
    physical = {name: config["input_dtypes"][name] for name in config["input_dtypes"]}
    source = re.sub(r"(?m)^FEATURES = .*", lambda _: "FEATURES = " + literal(required), source)
    source = re.sub(
        r"(?m)^PHYSICAL_DTYPES = .*", lambda _: "PHYSICAL_DTYPES = " + literal(physical), source
    )
    imports, helpers = [], []
    resources = []
    if plan.derived is None and plan.imputation is None:
        resources.append("derived_runtime_v1.py")
    if plan.temporal is None:
        resources.append("temporal_runtime_v1.py")
    resources.append("cleaning_runtime_v1.py")
    for resource in resources:
        extra_imports, extra_helpers = template_parts(
            files("mlstudio").joinpath(resource).read_text(encoding="utf-8")
        )
        imports.extend(i for i in extra_imports if "from mlstudio." not in i)
        helpers.extend(extra_helpers)
    indicators = (
        {column.indicator for column in plan.imputation.columns.values() if column.indicator}
        if plan.imputation
        else set()
    )
    guarded = [
        f.name
        for f in plan.features
        if not plan.imputation
        or (f.name not in plan.imputation.columns and f.name not in indicators)
    ]
    prefix = "\n".join(
        [
            "# cleaning-v1: row-wise prediction cleaning; selection is training-only.",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "CleaningFeatures = register_cleaning_transformer()",
            "CLEANING_CONFIG = " + literal(config),
            "CLEANING_ROW_CONFIG = " + literal(row_config),
            "CLEANING_GUARD_FEATURES = " + literal(guarded),
            "",
            "",
        ]
    )
    selected = "CleaningFeatures(CLEANING_ROW_CONFIG).transform(frame)"
    observed = "CleaningFeatures(CLEANING_ROW_CONFIG).transform(X_train)"
    if plan.temporal:
        selected = "TemporalFeatures(TEMPORAL_CONFIG).transform(" + selected + ")"
        observed = "TemporalFeatures(TEMPORAL_CONFIG).transform(" + observed + ")"
    if plan.derived:
        selected = "DerivedFeatures(DERIVED_CONFIG).transform(" + selected + ")"
        observed = "DerivedFeatures(DERIVED_CONFIG).transform(" + observed + ")"
    block = "        stage = 'preprocessing'\n"
    if plan.plan_version == "0.3":
        block += "        validate_multiclass_target(frame[TARGET], CLASSES)\n"
    block += "        selected_features, _ = cleaning_select(" + selected + ", CLEANING_CONFIG)\n"
    block += "        selected_raw = frame.loc[selected_features.index]\n"
    source = source.replace("        stage = 'target'\n", block + "        stage = 'target'\n")
    source = source.replace(
        "eligible = frame.loc[frame[TARGET].notna()]",
        "eligible = selected_raw.loc[selected_raw[TARGET].notna()]",
    )
    source = re.sub(r"(?m)^        eligible = frame$", "        eligible = selected_raw", source)
    source = source.replace(
        "model_pipeline = Pipeline(steps=[",
        "model_pipeline = Pipeline(steps=[('cleaning', CleaningFeatures(CLEANING_ROW_CONFIG)), ",
    )
    for function, args in [
        ("validate_training_partition", "y_train"),
        ("validate_regression_training", "y_train, y_test"),
        ("validate_multiclass_partition", "y_train, y_test, CLASSES"),
    ]:
        source = re.sub(
            rf"(?m)^        {function}\(.*$",
            lambda _, function=function, args=args: (
                f"        {function}({observed}[CLEANING_GUARD_FEATURES], {args})"
            ),
            source,
        )
    source = source.replace(
        "isinstance(error, WorkloadValidationError)",
        "isinstance(error, (WorkloadValidationError, CleaningValidationError))",
    ).replace(
        "isinstance(error, (WorkloadValidationError, ImputationValidationError))",
        "isinstance(error, (WorkloadValidationError, ImputationValidationError, "
        "CleaningValidationError))",
    )
    return prefix + source
