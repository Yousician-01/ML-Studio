"""Embed the exact versioned row-wise runtime in standalone generated workloads."""

import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.derived is None:
        return source
    config = plan.derived.model_dump(mode="json")
    outputs = set(config["output_types"])
    if plan.temporal is not None:
        outputs.update(feature.name for feature in plan.temporal.features)
    raw_features = [feature for feature in plan.features if feature.name not in outputs]
    physical = {
        plan.target.column: plan.target.physical_dtype,
        **{feature.name: feature.physical_dtype for feature in raw_features},
        **(plan.temporal.input_dtypes if plan.temporal is not None else {}),
        **config["input_dtypes"],
    }
    inputs = list(
        dict.fromkeys(
            [feature.name for feature in raw_features]
            + list(plan.temporal.sources if plan.temporal is not None else {})
            + list(config["input_dtypes"])
        )
    )
    imports, helpers = template_parts(
        files("mlstudio").joinpath("derived_runtime_v1.py").read_text(encoding="utf-8")
    )
    prefix = "\n".join(
        [
            "# derived-v1: bounded stateless expressions; no learned full-source statistics.",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "DerivedFeatures = register_derived_transformer()",
            "DERIVED_CONFIG = " + literal(config),
            "DERIVED_MODEL_FEATURES = " + literal([feature.name for feature in plan.features]),
            "",
            "",
        ]
    )
    for marker in ["\nFEATURES = ", "\nPHYSICAL_DTYPES = ", "model_pipeline = Pipeline(steps=["]:
        if source.count(marker) != 1:
            raise ValueError("Generated derived integration point is unavailable.")
    source = re.sub(r"(?m)^FEATURES = .*", lambda _: "FEATURES = " + literal(inputs), source)
    source = re.sub(
        r"(?m)^PHYSICAL_DTYPES = .*", lambda _: "PHYSICAL_DTYPES = " + literal(physical), source
    )
    step = "('derived', DerivedFeatures(DERIVED_CONFIG)), "
    if plan.temporal is not None:
        marker = "('temporal', TemporalFeatures(TEMPORAL_CONFIG)), "
        source = source.replace(marker, marker + step)
        # Temporal integration already rewrote these validation calls.
        source = source.replace(
            "TemporalFeatures(TEMPORAL_CONFIG).transform(X_train)[MODEL_FEATURES]",
            "DerivedFeatures(DERIVED_CONFIG).transform("
            "TemporalFeatures(TEMPORAL_CONFIG).transform(X_train))[DERIVED_MODEL_FEATURES]",
        )
    else:
        marker = "model_pipeline = Pipeline(steps=["
        source = source.replace(marker, marker + step)
        for function in [
            "validate_training_partition",
            "validate_regression_training",
            "validate_multiclass_partition",
        ]:
            source = source.replace(
                "        " + function + "(X_train,",
                "        " + function + "(DerivedFeatures(DERIVED_CONFIG).transform(X_train)"
                "[DERIVED_MODEL_FEATURES],",
            )
    return prefix + source
