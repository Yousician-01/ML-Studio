"""Embed train-fitted imputation after stateless stages, before existing branches."""

import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.imputation is None:
        return source
    config = plan.imputation.model_dump(mode="json")
    outputs = {c.indicator for c in plan.imputation.columns.values() if c.indicator}
    if plan.temporal is not None:
        outputs.update(f.name for f in plan.temporal.features)
    if plan.derived is not None:
        outputs.update(f.name for f in plan.derived.features)
    raw_features = [f for f in plan.features if f.name not in outputs]
    physical = {
        plan.target.column: plan.target.physical_dtype,
        **{f.name: f.physical_dtype for f in raw_features},
        **(plan.temporal.input_dtypes if plan.temporal else {}),
        **(plan.derived.input_dtypes if plan.derived else {}),
        **config["input_dtypes"],
    }
    inputs = [name for name in physical if name != plan.target.column]
    for marker in ["\nFEATURES = ", "\nPHYSICAL_DTYPES = ", "model_pipeline = Pipeline(steps=["]:
        if source.count(marker) != 1:
            raise ValueError("Generated imputation integration point is unavailable.")
    source = re.sub(r"(?m)^FEATURES = .*", lambda _: "FEATURES = " + literal(inputs), source)
    source = re.sub(
        r"(?m)^PHYSICAL_DTYPES = .*", lambda _: "PHYSICAL_DTYPES = " + literal(physical), source
    )
    imports, helpers = [], []
    if plan.derived is None:
        imports, helpers = template_parts(
            files("mlstudio").joinpath("derived_runtime_v1.py").read_text(encoding="utf-8")
        )
    extra_imports, extra_helpers = template_parts(
        files("mlstudio").joinpath("imputation_runtime_v1.py").read_text(encoding="utf-8")
    )
    imports.extend(i for i in extra_imports if "from mlstudio." not in i)
    helpers.extend(extra_helpers)
    indicators = {c.indicator for c in plan.imputation.columns.values() if c.indicator}
    guarded = [
        f.name
        for f in plan.features
        if f.name not in plan.imputation.columns and f.name not in indicators
    ]
    prefix = "\n".join(
        [
            "# imputation-v1: statistics are learned exclusively inside pipeline.fit(X_train).",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "ImputationFeatures = register_imputation_transformer()",
            "IMPUTATION_CONFIG = " + literal(config),
            "IMPUTATION_GUARD_FEATURES = " + literal(guarded),
            "",
            "",
        ]
    )
    step = "('advanced_imputation', ImputationFeatures(IMPUTATION_CONFIG)), "
    if plan.derived is not None:
        marker = "('derived', DerivedFeatures(DERIVED_CONFIG)), "
    elif plan.temporal is not None:
        marker = "('temporal', TemporalFeatures(TEMPORAL_CONFIG)), "
    else:
        marker = "model_pipeline = Pipeline(steps=["
    source = source.replace(marker, marker + step)
    observed = "X_train"
    if plan.temporal is not None:
        observed = "TemporalFeatures(TEMPORAL_CONFIG).transform(" + observed + ")"
    if plan.derived is not None:
        observed = "DerivedFeatures(DERIVED_CONFIG).transform(" + observed + ")"
    observed += "[IMPUTATION_GUARD_FEATURES]"
    # Retain split/label checks and unhandled all-missing feature checks. Advanced
    # columns are checked by their actual fit/transform, allowing constant fallback.
    for function, args in [
        ("validate_training_partition", "y_train"),
        ("validate_regression_training", "y_train, y_test"),
        ("validate_multiclass_partition", "y_train, y_test, CLASSES"),
    ]:
        source = re.sub(
            rf"(?m)^        {function}\(.*$",
            lambda _, function=function, args=args: f"        {function}({observed}, {args})",
            source,
        )
    source = source.replace(
        "isinstance(error, WorkloadValidationError)",
        "isinstance(error, (WorkloadValidationError, ImputationValidationError))",
    )
    return prefix + source
