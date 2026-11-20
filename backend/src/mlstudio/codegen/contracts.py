"""Newly resolved plans opt into portable schema guards; old plans stay unchanged."""

import ast
import re
from importlib.resources import files

from mlstudio.codegen.render import literal, template_parts


def extend_source(source, plan):
    if plan.schema_contract is None:
        return source
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"FEATURES", "PHYSICAL_DTYPES"}
    }
    metadata = {c["name"]: c for c in plan.schema_contract["raw_inputs"]}
    contract = {
        "version": "schema-contract-v1",
        "extra_columns": "ignored",
        "target_excluded": plan.target.column,
        "raw_inputs": [
            {
                **metadata.get(name, {}),
                "name": name,
                "physical_dtype": constants["PHYSICAL_DTYPES"].get(name),
            }
            for name in constants["FEATURES"]
            if name != plan.target.column
        ],
    }
    imports, helpers = template_parts(
        files("mlstudio").joinpath("schema_runtime_v1.py").read_text(encoding="utf-8")
    )
    prefix = "\n".join(
        [
            "# schema-contract-v1: raw shape and frozen estimator-facing schema.",
            *imports,
            "",
            "\n\n".join(helpers),
            "",
            "RawInputs, ContractPreprocessor = register_schema_transformers()",
            "RAW_SCHEMA_CONTRACT = " + literal(contract),
            "",
            "",
        ]
    )
    source = source.replace(
        "model_pipeline = Pipeline(steps=[",
        "model_pipeline = Pipeline(steps=[('raw_schema', RawInputs(RAW_SCHEMA_CONTRACT)), ",
    )
    for marker in [
        "('preprocessor', SelectedPreprocessor(preprocessor, SELECTION_CONFIG))",
        "('preprocessor', preprocessor)",
    ]:
        if marker in source:
            inner = marker[len("('preprocessor', ") : -1]
            source = source.replace(marker, "('preprocessor', ContractPreprocessor(" + inner + "))")
            break
    else:
        raise ValueError("Schema contract preprocessing integration point is unavailable.")
    marker = "        model_pipeline.fit(X_train, y_train)"
    source = source.replace(
        marker,
        marker + "\n        model_pipeline.schema_contract_ = {'raw': RAW_SCHEMA_CONTRACT, "
        "'estimator': model_pipeline.named_steps['preprocessor'].contract_}",
    )
    source = re.sub(
        r"isinstance\(error, (WorkloadValidationError|\(WorkloadValidationError[^)]*\))\)",
        lambda m: "isinstance(error, (" + m[1].strip("()") + ", SchemaContractError))",
        source,
    )
    return prefix + source
