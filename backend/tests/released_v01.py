"""Synthetic released-schema state, independent of current ORM/default builders.

The database is created by the real migrations through the released revision.
Historical Python comes from a pinned v1 golden, never the current generator.
The tiny complete fitted model is produced locally; no user DB/data/model is read.
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import joblib
import pandas as pd
from alembic.config import Config
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sqlalchemy import MetaData, Table, inspect, select

from alembic import command
from mlstudio.db.session import create_database_engine

BACKEND = Path(__file__).resolve().parents[1]
RELEASED_HEAD = "0005_tracking"
GOLDEN_HASHES = {
    "decision_tree": "62108ef3175a916bc292b636c533e61528d57f5630d703e8309c35ed5c5537f3",
    "l1": "e291acbf70cd0f3fd476216ff0a413a1561c0d38392583ea1c5c42876f28f145",
    "mixed": "83fedce75a232337f13a12c0d1ec62dfb8a0140400bd04b9556e5865514b8c58",
    "numeric": "240467a817701fa412a4ce1bac43492defc7ed37a083e41d285a9c22e709e728",
    "random_forest": "fae32f1c36706367f375108236cde811683afca2b57881ae3b1688173435f315",
    "unstratified": "6890634d8011b5eab40197281fb083055bc5d47f91d9f716025fc97a285bc2f9",
}
PROJECTS = {
    name: f"10000000-0000-4000-8000-{i:012d}"
    for i, name in enumerate(("empty", "incomplete", "replaced", "other"), 1)
}
DATASETS = {
    name: f"20000000-0000-4000-8000-{i:012d}"
    for i, name in enumerate(("historical", "replacement", "incomplete", "other"), 1)
}
RUNS = {
    name: f"30000000-0000-4000-8000-{i:012d}" for i, name in enumerate(("success", "failed"), 1)
}
VERSIONS = {
    "pandas": "3.0.6",
    "numpy": "2.5.3",
    "scikit-learn": "1.9.1",
    "joblib": "1.5.3",
    "scipy": "1.18.1",
}
CREATED = "2026-10-01T10:00:00.000000Z"
STARTED = "2026-10-01T10:01:00.000000Z"
FINISHED = "2026-10-01T10:02:00.000000Z"
EMPTY_IR = {
    "ir_version": "0.1",
    "dataset": None,
    "target": None,
    "features": {},
    "model": None,
    "split": None,
}
POSITIVE = {"value_type": "string", "value": "yes"}
NEGATIVE = {"value_type": "string", "value": "no"}


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def migration_config(settings):
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["settings"] = settings
    return config


def encoded(value):
    # Deliberately retain pretty JSON. Migration must preserve stored text, not
    # deserialize/reserialize it to the newest application's preferred encoding.
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode()


def write_reference(home, relative, data):
    path = home / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": relative, "sha256": sha(data), "size_bytes": len(data)}


def dataset_row(home, name, project, rows):
    dataset_id = DATASETS[name]
    # CRLF + BOM is intentional: source bytes must not be normalized by an upgrade.
    data = b"\xef\xbb\xbfage,target\r\n" + b"".join(
        f"{i},{'yes' if i % 2 else 'no'}\r\n".encode() for i in range(rows)
    )
    relative = f"projects/{project}/datasets/{dataset_id}/source.csv"
    ref = write_reference(home, relative, data)
    return {
        "id": dataset_id,
        "project_id": project,
        "original_filename": f"{name}.csv",
        "format": "csv",
        "created_at": CREATED,
        "fingerprint": ref["sha256"],
        "source_relative_path": relative,
        "size_bytes": len(data),
        "row_count": rows,
        "column_count": 2,
        "missing_cells": 0,
        "duplicate_rows": 0,
        "parsing_version": "csv-utf8-v1",
        "pandas_version": VERSIONS["pandas"],
        "columns": [
            {
                "name": column,
                "source_order": order,
                "physical_dtype": dtype,
                "missing_count": 0,
                "unique_count": unique,
                "inferred_semantic_type": semantic,
                "semantic_override": None,
                "inference_version": "semantic-v2",
            }
            for order, (column, dtype, unique, semantic) in enumerate(
                [
                    ("age", "int64", rows, "continuous"),
                    ("target", "str", 2, "binary"),
                ]
            )
        ],
    }


def recipe(dataset):
    return {
        "ir_version": "0.1",
        "dataset": {"dataset_id": dataset["id"], "fingerprint": dataset["fingerprint"]},
        "target": {
            "column": "target",
            "positive_class": POSITIVE,
            "missing_value_policy": "exclude_rows",
        },
        "features": {"age": {"included": True, "operations": []}},
        "model": {
            "type": "logistic_regression",
            "parameters": {"C": 1.0, "penalty": "l2", "max_iter": 1000},
        },
        "split": {"test_size": 0.2, "random_seed": 42, "stratify": True},
    }


def frozen_plan(dataset):
    return {
        "plan_version": "0.1",
        "ir_version": "0.1",
        "generator": "mlstudio-python-v1",
        "dataset": recipe(dataset)["dataset"],
        "source": {
            "parser": "csv-utf8-v1",
            "size_bytes": dataset["size_bytes"],
            "encoding": "utf-8-sig",
            "missing_values": "pandas-default",
            "integer_policy": "lossless-precision-risk-reread",
        },
        "target": {
            "column": "target",
            "physical_dtype": "str",
            "semantic_type": "binary",
            "positive_class": POSITIVE,
            "negative_class": NEGATIVE,
            "missing_value_policy": "exclude_rows",
        },
        "features": [
            {
                "name": "age",
                "physical_dtype": "int64",
                "semantic_type": "continuous",
                "operations": [],
            }
        ],
        "split": recipe(dataset)["split"],
        "model": {
            "name": "LogisticRegression",
            "parameters": {
                "C": 1.0,
                "penalty": "l2",
                "max_iter": 1000,
                "solver": "lbfgs",
                "l1_ratio": 0.0,
                "dual": False,
                "tol": 0.0001,
                "fit_intercept": True,
                "intercept_scaling": 1,
                "class_weight": None,
                "random_state": 42,
                "verbose": 0,
                "warm_start": False,
            },
        },
        "implementation": {
            "version": "sklearn-local-v1",
            "libraries": VERSIONS,
            "python": "3.14.2",
            "grouping": "one-branch-per-feature-source-order",
            "remainder": "drop",
            "sparse_threshold": 1.0,
            "empty_training_feature": "fail",
        },
        "runtime": {
            "version": "cli-v1",
            "arguments": ["--dataset", "--result", "--model"],
            "result_schema": "mlstudio-result-v1",
            "model_format": "joblib-complete-pipeline",
        },
        "evaluation": {
            "metrics": ["accuracy", "precision", "recall", "f1", "roc_auc"],
            "zero_division": 0,
            "confusion_order": "negative-positive",
            "roc_auc": "positive-score-or-unavailable",
        },
    }


def historical_python(dataset):
    data = (BACKEND / "tests/golden/numeric.py.txt").read_bytes()
    assert sha(data) == "sha256:" + GOLDEN_HASHES["numeric"]
    source = data.decode()
    for old, new in (
        ("DATASET_ID = '11111111-1111-4111-8111-111111111111'", f"DATASET_ID = '{dataset['id']}'"),
        (
            "DATASET_FINGERPRINT = 'sha256:" + "a" * 64 + "'",
            f"DATASET_FINGERPRINT = '{dataset['fingerprint']}'",
        ),
        ("SOURCE_SIZE = 200", f"SOURCE_SIZE = {dataset['size_bytes']}"),
    ):
        assert source.count(old) == 1
        source = source.replace(old, new)
    return source.encode()


def fitted_result(home, dataset, plan, relative):
    """Tiny actual fitted pipeline; no external process or MLflow store is needed."""
    frame = pd.read_csv(home / dataset["source_relative_path"], encoding="utf-8-sig")
    x_train, x_test, y_train, y_test = train_test_split(
        frame[["age"]], frame.target, test_size=0.2, random_state=42, stratify=frame.target
    )
    model = Pipeline(
        [
            (
                "preprocessor",
                ColumnTransformer(
                    [("feature_000", "passthrough", ["age"])],
                    remainder="drop",
                    sparse_threshold=1.0,
                ),
            ),
            ("model", LogisticRegression(**plan["model"]["parameters"])),
        ]
    ).fit(x_train, y_train)
    predictions = model.predict(x_test)
    matrix = confusion_matrix(y_test, predictions, labels=["no", "yes"]).tolist()
    (tn, fp), (fn, tp) = matrix
    scores = model.predict_proba(x_test)[:, list(model.classes_).index("yes")]
    path = home / relative / "model.joblib"
    joblib.dump(model, path, compress=3, protocol=5)
    model_ref = {
        "path": path.relative_to(home).as_posix(),
        "sha256": sha(path.read_bytes()),
        "size_bytes": path.stat().st_size,
    }
    result = {
        "schema_version": "mlstudio-result-v1",
        "status": "success",
        "dataset": plan["dataset"],
        "generator": plan["generator"],
        "metrics": {
            "accuracy": (tn + tp) / 4,
            "precision": tp / (tp + fp) if tp + fp else 0,
            "recall": tp / (tp + fn) if tp + fn else 0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
            "roc_auc": float(roc_auc_score(y_test == "yes", scores)),
        },
        "roc_auc_unavailable_reason": None,
        "confusion_matrix": {"labels": [NEGATIVE, POSITIVE], "values": matrix},
        "population": {"source": 20, "eligible": 20, "training": 16, "test": 4},
        "artifacts": {"model": {"kind": "complete_pipeline", "filename": "model.joblib"}},
        "versions": {"python": "3.14.2", **VERSIONS},
    }
    return result, model_ref


def run_row(home, name, dataset):
    run_id, project_id = RUNS[name], PROJECTS["replaced"]
    relative = f"projects/{project_id}/runs/{run_id}"
    plan = frozen_plan(dataset)
    artifacts = {
        filename: write_reference(home, f"{relative}/{filename}", data)
        for filename, data in {
            "pipeline_ir.json": encoded(recipe(dataset)),
            "execution_plan.json": encoded(plan),
            "generated_run.py": historical_python(dataset),
        }.items()
    }
    provenance = {
        "mlstudio": "0.1.0",
        "executor": "local-subprocess-v1",
        "generator": "mlstudio-python-v1",
        "python": "3.14.2",
        **VERSIONS,
    }
    manifest = {
        "version": "mlstudio-package-v1",
        "run_id": run_id,
        "project_id": project_id,
        "dataset_id": dataset["id"],
        "revision": 15 if name == "success" else 16,
        "created_at": CREATED,
        "dataset": {
            "path": dataset["source_relative_path"],
            "sha256": dataset["fingerprint"],
            "size_bytes": dataset["size_bytes"],
        },
        "inputs": deepcopy(artifacts),
        "provenance": provenance,
        "population": {"source": 20, "eligible": 20},
    }
    artifacts["package.json"] = write_reference(home, f"{relative}/package.json", encoded(manifest))
    result = None
    if name == "success":
        result, artifacts["model.joblib"] = fitted_result(home, dataset, plan, relative)
        artifacts["result.json"] = write_reference(home, f"{relative}/result.json", encoded(result))
    for filename in ("stdout.log", "stderr.log"):
        artifacts[filename] = write_reference(home, f"{relative}/{filename}", b"")
    return {
        "id": run_id,
        "project_id": project_id,
        "dataset_id": dataset["id"],
        "sequence": 1 if name == "success" else 2,
        "request_id": f"40000000-0000-4000-8000-{1 if name == 'success' else 2:012d}",
        "revision": manifest["revision"],
        "source_sha256": artifacts["generated_run.py"]["sha256"],
        "plan_sha256": artifacts["execution_plan.json"]["sha256"],
        "state": "SUCCEEDED" if name == "success" else "FAILED",
        "created_at": CREATED,
        "started_at": STARTED,
        "finished_at": FINISHED,
        "manifest": manifest,
        "artifacts": artifacts,
        "summary": {
            "model": plan["model"],
            "split": plan["split"],
            "target": plan["target"],
            "dataset_fingerprint": dataset["fingerprint"],
        },
        "result": result,
        "failure": None
        if result
        else {
            "code": "nonzero_exit",
            "stage": "training",
            "message": "Execution did not complete successfully.",
        },
        "mlflow_run_id": "a" * 32 if name == "success" else "b" * 32,
        "tracking_status": "SYNCHRONIZED",
        "tracking_error": None,
        "tracking_updated_at": FINISHED,
    }


def build_released_workspace(settings):
    command.upgrade(migration_config(settings), RELEASED_HEAD)
    home = settings.home
    datasets = [
        dataset_row(home, "historical", PROJECTS["replaced"], 20),
        dataset_row(home, "replacement", PROJECTS["replaced"], 24),
        dataset_row(home, "incomplete", PROJECTS["incomplete"], 8),
        dataset_row(home, "other", PROJECTS["other"], 6),
    ]
    projects = [
        {
            "id": project_id,
            "name": name,
            "description": None,
            "problem_statement": "Predict a synthetic label",
            "success_context": None,
            "ml_objective": "binary_classification",
            "created_at": CREATED,
            "updated_at": FINISHED,
            "active_dataset_id": None,
            "target_column": None,
            "working_pipeline": deepcopy(EMPTY_IR),
            "revision": revision,
            "next_run_sequence": 3 if name == "replaced" else 1,
        }
        for (name, project_id), revision in zip(PROJECTS.items(), (3, 9, 17, 4), strict=True)
    ]
    projects[1]["working_pipeline"] = recipe(datasets[2])
    projects[1]["working_pipeline"]["target"]["positive_class"] = None
    projects[1]["working_pipeline"].update(model=None, split=None)
    projects[2]["working_pipeline"] = recipe(datasets[0])  # Old source stays explicitly stale.
    runs = [run_row(home, name, datasets[0]) for name in RUNS]
    engine = create_database_engine(settings)
    try:
        metadata = MetaData()
        tables = {
            name: Table(name, metadata, autoload_with=engine)
            for name in ("projects", "datasets", "runs")
        }
        with engine.begin() as connection:
            connection.execute(tables["projects"].insert(), projects)
            connection.execute(tables["datasets"].insert(), datasets)
            for index, dataset in ((1, datasets[2]), (2, datasets[1]), (3, datasets[3])):
                connection.execute(
                    tables["projects"]
                    .update()
                    .where(tables["projects"].c.id == projects[index]["id"])
                    .values(
                        active_dataset_id=dataset["id"],
                        target_column="target" if index == 1 else None,
                    )
                )
            connection.execute(tables["runs"].insert(), runs)
    finally:
        engine.dispose()


def snapshot(settings):
    """Capture SQL values as stored (including JSON text), schema and artifact bytes."""
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            rows = {
                name: [
                    tuple(row)
                    # Fixed table names only; never an external SQL identifier.
                    for row in connection.exec_driver_sql(f"SELECT * FROM {name} ORDER BY id")
                ]
                for name in ("projects", "datasets", "runs")
            }
            inspector = inspect(connection)
            schema = {
                name: {
                    "columns": [
                        (c["name"], str(c["type"]), c["nullable"], c["default"])
                        for c in inspector.get_columns(name)
                    ],
                    "foreign_keys": inspector.get_foreign_keys(name),
                    "primary_key": inspector.get_pk_constraint(name),
                    "unique": inspector.get_unique_constraints(name),
                    "indexes": inspector.get_indexes(name),
                    "checks": {
                        c["name"]: c["sqltext"] for c in inspector.get_check_constraints(name)
                    },
                }
                for name in rows
            }
            heads = tuple(
                connection.execute(
                    select(
                        Table("alembic_version", MetaData(), autoload_with=connection).c.version_num
                    )
                ).scalars()
            )
            foreign_keys = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            tables = tuple(sorted(inspector.get_table_names()))
        files = {
            path.relative_to(settings.home).as_posix(): path.read_bytes()
            for path in (settings.home / "projects").rglob("*")
            if path.is_file()
        }
        return {
            "rows": rows,
            "schema": schema,
            "heads": heads,
            "files": files,
            "foreign_key_errors": foreign_keys,
            "tables": tables,
        }
    finally:
        engine.dispose()


def assert_preserved(before, after, *, objective_changed=False):
    assert after["rows"] == before["rows"]
    assert after["files"] == before["files"]
    assert after["foreign_key_errors"] == before["foreign_key_errors"] == []
    assert after["tables"] == before["tables"]
    old_schema, new_schema = deepcopy(before["schema"]), deepcopy(after["schema"])
    if objective_changed:
        del old_schema["projects"]["checks"]["ck_project_objective"]
        del new_schema["projects"]["checks"]["ck_project_objective"]
    for table in old_schema:
        for kind in old_schema[table]:
            assert new_schema[table][kind] == old_schema[table][kind], (
                table,
                kind,
                new_schema[table][kind],
                old_schema[table][kind],
            )
