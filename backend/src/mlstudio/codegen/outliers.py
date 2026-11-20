"""Extend frozen generated workloads without changing legacy rendering."""

import ast
import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.outlier_treatment is None and plan.feature_selection is None:
        return source
    imports, helpers = template_parts(
        files("mlstudio").joinpath("outlier_runtime_v1.py").read_text(encoding="utf-8")
    )
    prefix = "\n".join(
        [
            "# Training-only outlier-treatment-v1 and feature-selection-v1.",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "OutlierFeatures, SelectedPreprocessor = register_outlier_transformers()",
            "",
            "",
        ]
    )
    if plan.outlier_treatment is not None:
        config = plan.outlier_treatment.model_dump(mode="json")
        outputs = {
            name
            for feature in config["features"]
            for name in [feature["name"], feature["indicator"]]
            if name
        }
        produced = set(outputs)
        for field in [plan.temporal, plan.derived, plan.feature_engineering]:
            if field:
                produced.update(f.name for f in field.features)
        if plan.imputation:
            produced.update(c.indicator for c in plan.imputation.columns.values() if c.indicator)
        constants = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"FEATURES", "PHYSICAL_DTYPES"}
        }
        inputs = list(dict.fromkeys([*constants["FEATURES"], *config["input_dtypes"]]))
        inputs = [name for name in inputs if name not in produced and name != plan.target.column]
        physical = {
            name: dtype
            for name, dtype in constants["PHYSICAL_DTYPES"].items()
            if name not in produced
        }
        physical.update(config["input_dtypes"])
        source = re.sub(r"(?m)^FEATURES = .*", lambda _: "FEATURES = " + literal(inputs), source)
        source = re.sub(
            r"(?m)^PHYSICAL_DTYPES = .*", lambda _: "PHYSICAL_DTYPES = " + literal(physical), source
        )
        prefix += "OUTLIER_CONFIG = " + literal(config) + "\n\n"
        marker = "('preprocessor', preprocessor)"
        source = source.replace(marker, "('outliers', OutlierFeatures(OUTLIER_CONFIG)), " + marker)
        advanced = set(plan.imputation.columns) if plan.imputation else set()
        indicators = (
            {c.indicator for c in plan.imputation.columns.values() if c.indicator}
            if plan.imputation
            else set()
        )
        engineered = (
            {f.name for f in plan.feature_engineering.features}
            if plan.feature_engineering
            else set()
        )
        guarded = [
            f.name
            for f in plan.features
            if f.name not in outputs | advanced | indicators | engineered
        ]
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
    if plan.feature_selection is not None:
        selected = set(plan.feature_selection.features)
        config = {
            **plan.feature_selection.model_dump(mode="json"),
            "branches": {
                feature.name: f"feature_{index:03d}"
                for index, feature in enumerate(plan.features)
                if feature.name in selected
            },
        }
        if set(config["branches"]) != selected:
            raise ValueError("Variance selection references absent model branches.")
        prefix += "SELECTION_CONFIG = " + literal(config) + "\n\n"
        source = source.replace(
            "('preprocessor', preprocessor)",
            "('preprocessor', SelectedPreprocessor(preprocessor, SELECTION_CONFIG))",
        )
    source = re.sub(
        r"isinstance\(error, (WorkloadValidationError|\(WorkloadValidationError[^)]*\))\)",
        lambda m: "isinstance(error, (" + m[1].strip("()") + ", OutlierValidationError))",
        source,
    )
    return prefix + source
