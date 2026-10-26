"""Pure v2 adapter: reuse fixed v1 preparation/literal/I/O helpers without changing v1."""

import ast
from importlib.resources import files
from string import Template

from mlstudio.codegen.render import (
    CSV_FUNCTIONS,
    CSV_IMPORTS,
    IMPORTS,
    RUNTIME_FUNCTIONS,
    constructor,
    literal,
    template_parts,
)
from mlstudio.codegen.v2.schemas import RegressionPlan, evaluation_context, plan_sha256

HELPER_SOURCE = (
    files("mlstudio.codegen.v2").joinpath("workload_runtime.py").read_text(encoding="utf-8")
)
REGRESSION_IMPORTS, REGRESSION_FUNCTIONS = template_parts(HELPER_SOURCE)
REGRESSION_IMPORTS = [line for line in REGRESSION_IMPORTS if not line.startswith("from mlstudio.")]
COMMON_NAMES = {
    "WorkloadValidationError",
    "verify_environment",
    "read_verified_bytes",
    "write_result",
    "write_model",
    "runtime_paths",
}
COMMON_FUNCTIONS = [
    source for source in RUNTIME_FUNCTIONS if ast.parse(source).body[0].name in COMMON_NAMES
]
COMMON_IMPORTS = [
    "import hashlib",
    "import json",
    "import os",
    "import platform",
    "import tempfile",
    "from importlib.metadata import version",
    "from pathlib import Path",
    "import joblib",
]


def generate(plan):
    plan = RegressionPlan.model_validate(plan.model_dump(mode="json"))
    operators = sorted({op.name for feature in plan.features for op in feature.operations})
    imports = sorted(
        set(
            CSV_IMPORTS
            + COMMON_IMPORTS
            + REGRESSION_IMPORTS
            + [f"from {IMPORTS[name]} import {name}" for name in operators]
            + [f"from sklearn.linear_model import {plan.model.estimator}"]
        )
    )
    branches = []
    for index, feature in enumerate(plan.features):
        label = literal(f"feature_{index:03d}")
        if feature.operations:
            branches.append(f"                ({label}, Pipeline(steps=[")
            for number, op in enumerate(feature.operations):
                branches.append(f"                    ('step_{number}', {constructor(op, 24)}),")
            branches.append(f"                ]), {literal([feature.name])}),")
        else:
            branches.append(f"                ({label}, 'passthrough', {literal([feature.name])}),")
    parameters = "\n".join(
        f"            {name}={literal(value)},"
        for name, value in sorted(plan.model.parameters.model_dump().items())
    )
    constants = {
        "DATASET_ID": plan.dataset.dataset_id,
        "DATASET_FINGERPRINT": plan.dataset.fingerprint,
        "SOURCE_SIZE": plan.source.size_bytes,
        "LIBRARIES": plan.implementation.libraries,
        "PYTHON_VERSION": plan.implementation.python,
        "TARGET": plan.target.column,
        "FEATURES": [feature.name for feature in plan.features],
        "PHYSICAL_DTYPES": {
            plan.target.column: plan.target.physical_dtype,
            **{feature.name: feature.physical_dtype for feature in plan.features},
        },
        "SOURCE_CONTRACT": plan.source.model_dump(mode="json"),
        "MODEL_CONTRACT": plan.model.model_dump(mode="json"),
        "EVALUATION_CONTEXT": evaluation_context(plan),
        "PLAN_SHA256": plan_sha256(plan),
        "GENERATOR": plan.generator,
        "IMPLEMENTATION_VERSION": plan.implementation.version,
    }
    main = Template("""def main():
    parser = argparse.ArgumentParser(description='ML Studio regression workload')
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--result', required=True)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    result_path = None
    stage = 'runtime_inputs'
    try:
        dataset_path, result_path, model_path = runtime_paths(args.dataset, args.result, args.model)
        verify_environment(LIBRARIES, PYTHON_VERSION)
        source_sha256 = 'sha256:' + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        stage = 'data_loading'
        source_bytes = read_verified_bytes(dataset_path, DATASET_FINGERPRINT, SOURCE_SIZE)
        frame = parse_csv_bytes(source_bytes)
        if any(name not in frame or str(frame[name].dtype) != dtype
               for name, dtype in PHYSICAL_DTYPES.items()):
            raise ValueError('Source interpretation differs from the resolved plan.')
        stage = 'target'
        eligible = frame.loc[frame[TARGET].notna()]
        y = numeric_target(eligible[TARGET])
        X = eligible[FEATURES]
        # Split before learning imputation, scaling, or category vocabulary.
        stage = 'split'
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=$test_size, random_state=$seed, stratify=None, shuffle=True)
        stage = 'training_partition_validation'
        validate_regression_training(X_train, y_train, y_test)
        stage = 'preprocessing'
        preprocessor = ColumnTransformer(
            transformers=[
$branches
            ], remainder='drop', sparse_threshold=1.0,
            n_jobs=1, verbose=False, verbose_feature_names_out=True)
        regressor = $estimator(
$parameters
        )
        model_pipeline = Pipeline(steps=[('preprocessor', preprocessor), ('model', regressor)])
        stage = 'training'
        model_pipeline.fit(X_train, y_train)
        stage = 'evaluation'
        predictions = model_pipeline.predict(X_test)
        metrics, reason, constant = evaluate_regression(y_test, predictions)
        result = {
            'schema_version': 'mlstudio-result-v2', 'task': 'regression', 'status': 'success',
            'dataset': {'dataset_id': DATASET_ID, 'fingerprint': DATASET_FINGERPRINT},
            'source': SOURCE_CONTRACT, 'generator': GENERATOR,
            'implementation_version': IMPLEMENTATION_VERSION,
            'plan_sha256': PLAN_SHA256, 'source_sha256': source_sha256,
            'model': MODEL_CONTRACT, 'evaluation': EVALUATION_CONTEXT,
            'metrics': metrics, 'r2_unavailable_reason': reason, 'test_target_constant': constant,
            'population': {'source': len(frame), 'eligible': len(y),
                           'training': len(y_train), 'test': len(y_test)},
            'artifacts': {'model': {'kind': 'complete_pipeline', 'filename': model_path.name}},
            'versions': {'python': PYTHON_VERSION, **LIBRARIES},
        }
        json.dumps(result, allow_nan=False)
        stage = 'artifact_output'
        write_model(model_path, model_pipeline)
        write_result(result_path, result)
        return 0
    except Exception as error:
        failure = {'schema_version': 'mlstudio-result-v2', 'task': 'regression', 'status': 'failed',
                   'stage': stage,
                   'message': str(error) if isinstance(error, WorkloadValidationError)
                   else 'Workload failed; review stage and configuration.'}
        if result_path is not None:
            try:
                write_result(result_path, failure)
            except Exception:
                pass
        print('Workload failed during ' + stage + '.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
""").substitute(
        test_size=literal(plan.split.test_size),
        seed=literal(plan.split.random_seed),
        branches="\n".join(branches),
        estimator=plan.model.estimator,
        parameters=parameters,
    )
    sections = [
        f"# Generated by {plan.generator}. Immutable regression implementation contract.",
        "import argparse",
        "import sys",
        "from sklearn.compose import ColumnTransformer",
        "from sklearn.model_selection import train_test_split",
        "from sklearn.pipeline import Pipeline",
        *imports,
        "",
        "\n\n\n".join(CSV_FUNCTIONS + COMMON_FUNCTIONS + REGRESSION_FUNCTIONS),
        "",
        *[f"{name} = {literal(value)}" for name, value in constants.items()],
        "",
        "",
        main,
    ]
    return "\n".join(sections).replace("\r\n", "\n")
