"""Optional temporal-v1 source extension; legacy renderers and goldens stay intact."""

import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.temporal is None:
        return source
    for marker in ["\nFEATURES = ", "\nPHYSICAL_DTYPES = ", "model_pipeline = Pipeline(steps=["]:
        if source.count(marker) != 1:
            raise ValueError("Generated temporal integration point is unavailable.")
    config = plan.temporal.model_dump(mode="json")
    outputs = {feature["name"] for feature in config["features"]}
    inputs = list(
        dict.fromkeys(
            [feature.name for feature in plan.features if feature.name not in outputs]
            + list(config["sources"])
        )
    )
    physical = {
        plan.target.column: plan.target.physical_dtype,
        **{
            feature.name: feature.physical_dtype
            for feature in plan.features
            if feature.name not in outputs
        },
        **config["input_dtypes"],
    }
    imports, helpers = template_parts(
        files("mlstudio").joinpath("temporal_runtime_v1.py").read_text(encoding="utf-8")
    )
    # Fixed code, not Dataset-controlled Python. Serialize config exclusively as literals.
    prefix = "\n".join(
        [
            "# temporal-v1: stateless UTC features; explicit references, never the clock.",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "TemporalFeatures = register_temporal_transformer()",
            "TEMPORAL_CONFIG = " + literal(config),
            "MODEL_FEATURES = " + literal([feature.name for feature in plan.features]),
            "",
            "",
        ]
    )
    source = re.sub(r"(?m)^FEATURES = .*", lambda _: "FEATURES = " + literal(inputs), source)
    source = re.sub(
        r"(?m)^PHYSICAL_DTYPES = .*", lambda _: "PHYSICAL_DTYPES = " + literal(physical), source
    )
    source = source.replace(
        "model_pipeline = Pipeline(steps=[",
        "model_pipeline = Pipeline(steps=[('temporal', TemporalFeatures(TEMPORAL_CONFIG)), ",
    )
    # Validate the actual transformed training inputs, never excluded/raw source columns.
    for function in [
        "validate_training_partition",
        "validate_regression_training",
        "validate_multiclass_partition",
    ]:
        source = source.replace(
            "        " + function + "(X_train,",
            "        "
            + function
            + "(TemporalFeatures(TEMPORAL_CONFIG).transform(X_train)[MODEL_FEATURES],",
        )
    return prefix + source
