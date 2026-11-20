"""Embed portable train-fitted engineering before existing per-feature branches."""

import ast
import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.feature_engineering is None:
        return source
    config = plan.feature_engineering.model_dump(mode="json")
    outputs = {f["name"] for f in config["features"]}
    parsed = ast.parse(source)
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in parsed.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"FEATURES", "PHYSICAL_DTYPES"}
    }
    raw_inputs = [name for name in constants["FEATURES"] if name not in outputs]
    # Resolve source/temporal/derived dependencies to original raw inputs. Never
    # require a caller to send engineered columns or read the training Dataset.
    produced = set(outputs)
    if plan.temporal:
        produced.update(f.name for f in plan.temporal.features)
    if plan.derived:
        produced.update(f.name for f in plan.derived.features)
    if plan.imputation:
        produced.update(c.indicator for c in plan.imputation.columns.values() if c.indicator)
    physical = {
        name: dtype for name, dtype in constants["PHYSICAL_DTYPES"].items() if name not in produced
    }
    physical.update(config["input_dtypes"])
    # Resolved dtypes are raw source-only; including these also covers excluded
    # sources consumed exclusively by engineering, without exposing new paths.
    raw_inputs = list(dict.fromkeys([*raw_inputs, *config["input_dtypes"]]))
    raw_inputs = [
        name for name in raw_inputs if name not in produced and name != plan.target.column
    ]
    source = re.sub(r"(?m)^FEATURES = .*", lambda _: "FEATURES = " + literal(raw_inputs), source)
    source = re.sub(
        r"(?m)^PHYSICAL_DTYPES = .*", lambda _: "PHYSICAL_DTYPES = " + literal(physical), source
    )
    imports, helpers = [], []
    resources = []
    if plan.derived is None and plan.imputation is None and plan.cleaning is None:
        resources.append("derived_runtime_v1.py")
    resources.append("feature_engineering_runtime_v1.py")
    for resource in resources:
        extra_imports, extra_helpers = template_parts(
            files("mlstudio").joinpath(resource).read_text(encoding="utf-8")
        )
        imports.extend(i for i in extra_imports if "from mlstudio." not in i)
        helpers.extend(extra_helpers)
    prefix = "\n".join(
        [
            "# feature-engineering-v1: learned state fits training rows only.",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "EngineeringFeatures = register_engineering_transformer()",
            "ENGINEERING_CONFIG = " + literal(config),
            "",
            "",
        ]
    )
    marker = "('preprocessor', preprocessor)"
    if source.count(marker) != 1:
        raise ValueError("Feature engineering pipeline integration point is unavailable.")
    source = source.replace(
        marker, "('feature_engineering', EngineeringFeatures(ENGINEERING_CONFIG)), " + marker
    )
    # Pre-fit guards inspect earlier stages and unaffected estimator columns.
    # Engineered output completeness/domain is checked by the fitted transformer
    # and the existing output branch imputer/encoder, never a full-source fit.
    advanced = set(plan.imputation.columns) if plan.imputation else set()
    indicators = (
        {c.indicator for c in plan.imputation.columns.values() if c.indicator}
        if plan.imputation
        else set()
    )
    guarded = [f.name for f in plan.features if f.name not in outputs | advanced | indicators]
    observed = "X_train"
    for field, constructor, constant in [
        (plan.cleaning, "CleaningFeatures", "CLEANING_ROW_CONFIG"),
        (plan.temporal, "TemporalFeatures", "TEMPORAL_CONFIG"),
        (plan.derived, "DerivedFeatures", "DERIVED_CONFIG"),
    ]:
        if field is not None:
            observed = f"{constructor}({constant}).transform({observed})"
    for function, args in [
        ("validate_training_partition", "y_train"),
        ("validate_regression_training", "y_train, y_test"),
        ("validate_multiclass_partition", "y_train, y_test, CLASSES"),
    ]:
        source = re.sub(
            rf"(?m)^        {function}\(.*$",
            lambda _, function=function, args=args: (
                f"        {function}({observed}[{literal(guarded)}], {args})"
            ),
            source,
        )
    # Extend the existing sanitized workload-error whitelist only.
    source = re.sub(
        r"isinstance\(error, (WorkloadValidationError|\(WorkloadValidationError[^)]*\))\)",
        lambda m: "isinstance(error, (" + m[1].strip("()") + ", EngineeringValidationError))",
        source,
    )
    return prefix + source
