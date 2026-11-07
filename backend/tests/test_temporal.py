"""Small fixtures pin temporal semantics, compiler parity and historical compatibility."""

import importlib.util
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest


def column(name):
    return {"kind": "column", "name": name}


def test_advanced_imputation_diagnostics_and_ir_persistence(client, monkeypatch):
    from mlstudio.imputation_runtime_v1 import ImputationFeatures

    def refuse_fit(*args, **kwargs):
        raise AssertionError("Configuration previews must not fit statistics")

    monkeypatch.setattr(ImputationFeatures, "fit", refuse_fit)
    from test_projects_datasets import configure, create, upload

    project = create(client)
    upload(
        client, project, b"income,city,label\n10,Pune,yes\n,Pune,no\n30,Mumbai,yes\n,Mumbai,no\n"
    )
    configure(client, project, target_column="label")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    ir = state["ir"]
    ir["imputation"] = {
        "version": "imputation-v1",
        "columns": {
            "income": {
                "rules": [
                    {"condition": None, "strategy": "median", "value": None, "group_by": ["city"]}
                ],
                "fallback": {"strategy": "constant", "value": 5},
                "indicator": "income_was_missing",
                "previous_strategy": None,
            }
        },
    }
    body = {"revision": state["revision"], "ir": ir}
    preview = client.post(path + "/temporal-preview", json=body)
    assert preview.status_code == 200, preview.text
    evidence = preview.json()["imputation"]["income"]
    assert evidence["missing_count"] == 2 and evidence["rule_matches"] == [2]
    assert evidence["indicator_values"] == [0, 1, 0, 1]
    assert not any(c["name"] == "income" for c in preview.json()["columns"]), (
        "no fitted full-source values"
    )
    saved = client.patch(path, json=body)
    assert saved.status_code == 200, saved.text
    assert client.get(path).json()["ir"]["imputation"]["version"] == "imputation-v1"


def test_generalized_preview_persistence_and_train_validation(client):
    from test_projects_datasets import configure, create, upload

    project = create(client)
    upload(client, project, b"revenue,orders,label\n10,2,yes\n20,0,no\n30,3,yes\n40,4,no\n")
    configure(client, project, target_column="label")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    ir = state["ir"]
    ir["derived"] = {
        "version": "derived-v1",
        "features": [
            {
                "name": "ratio",
                "expression": call("safe_divide", column("revenue"), column("orders")),
            }
        ],
    }
    ir["features"]["ratio"] = {"included": True, "operations": []}
    ir["model"], ir["split"] = {"type": "logistic_regression"}, {}
    body = {"revision": state["revision"], "ir": ir}
    preview = client.post(path + "/temporal-preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["errors"] == []
    assert preview.json()["columns"][0]["values"] == [5.0, None, 10.0, 10.0]
    assert preview.json()["columns"][0]["invalid_count"] == 1
    saved = client.patch(path, json=body)
    assert saved.status_code == 200, saved.text
    assert any(
        i["code"] == "feature_missing_values" and i["column"] == "ratio"
        for i in saved.json()["issues"]
    )
    reopened = client.get(path).json()
    assert reopened["ir"]["derived"]["version"] == "derived-v1"
    assert reopened["columns"][-1]["effective_semantic_type"] == "continuous"
    invalid = reopened["ir"]
    invalid["derived"]["features"][0]["expression"] = column("label")
    result = client.post(
        path + "/temporal-preview", json={"revision": reopened["revision"], "ir": invalid}
    )
    assert result.status_code == 200 and result.json()["errors"]


def call(operation, *arguments, **parameters):
    return {
        "kind": "call",
        "operation": operation,
        "arguments": arguments,
        "parameters": parameters,
    }


def config(features, **sources):
    return {
        "version": "temporal-v1",
        "sources": sources,
        "features": [
            {"name": name, "expression": expression} for name, expression in features.items()
        ],
    }


def test_calendar_cycles_missing_age_timezone_and_strict_parsing():
    from mlstudio.temporal_runtime_v1 import temporal_transform
    from mlstudio.temporal_schemas import TemporalConfig

    source = pd.DataFrame(
        {
            "event": ["2024-02-29T23:00:00-02:00", None, "05/11/2026"],
            "birth": ["2000-02-29", None, "2000-01-01"],
        }
    )
    fixed = {"kind": "literal", "value": "2023-02-28T00:00:00Z"}
    definition = TemporalConfig.model_validate(
        config(
            {
                "hour": call("hour", column("event")),
                "weekend": call("is_weekend", column("event")),
                "age": call("calendar_age", column("birth"), fixed),
                "days": call("date_diff", fixed, column("birth"), unit="days"),
                "cycle": call("cyclic_cos", {"kind": "reference", "name": "hour"}),
            },
            event={"naive": "utc", "invalid": "coerce"},
            birth={"naive": "utc"},
        )
    )
    output, counts = temporal_transform(source, definition.model_dump(mode="json"))
    assert output.loc[0, "hour"] == 1  # Offset crosses midnight in UTC.
    assert output.loc[0, "age"] == 22  # Feb-29 anniversary is March 1 in non-leap years.
    assert output.loc[0, "days"] == 8400
    assert output.loc[0, "cycle"] == pytest.approx(np.cos(2 * np.pi / 24))
    assert output.loc[1, ["hour", "weekend", "age", "days", "cycle"]].isna().all()
    assert counts["event"]["invalid_count"] == 1
    strict = definition.model_dump(mode="json")
    strict["sources"]["event"]["invalid"] = "reject"
    with pytest.raises(ValueError, match="invalid"):
        temporal_transform(source, strict)
    # Adjacent periodic endpoints are neighbours, not distant linear values.
    cyclic = config(
        {
            "sin": call("cyclic_sin", call("month", column("event"))),
            "cos": call("cyclic_cos", call("month", column("event"))),
        },
        event={"naive": "utc"},
    )
    values, _ = temporal_transform(
        pd.DataFrame({"event": ["2024-01-01", "2024-12-01"]}),
        TemporalConfig.model_validate(cyclic).model_dump(mode="json"),
    )
    assert np.linalg.norm(values.loc[0, ["sin", "cos"]] - values.loc[1, ["sin", "cos"]]) < 0.6


def test_explicit_timezone_format_accepts_offset_before_the_date():
    from mlstudio.temporal_runtime_v1 import temporal_transform
    from mlstudio.temporal_schemas import TemporalConfig

    explicit = config(
        {"hour": call("hour", column("date"))},
        date={"format": "%z %Y-%m-%d %H:%M:%S", "naive": "reject"},
    )
    output, counts = temporal_transform(
        pd.DataFrame({"date": ["+0530 2026-11-07 10:00:00"]}),
        TemporalConfig.model_validate(explicit).model_dump(mode="json"),
    )
    assert output.loc[0, "hour"] == 4 and counts["date"]["invalid_count"] == 0


def test_expression_validation_rejects_cycles_types_duplicates_and_target():
    from mlstudio.temporal_schemas import TemporalConfig, validate_temporal

    source = {"date": "datetime", "amount": "continuous", "target": "datetime"}
    bad = [
        config({"a": call("year", column("amount"))}),
        config({"a": {"kind": "reference", "name": "b"}, "b": {"kind": "reference", "name": "a"}}),
        config({"a": call("year", column("missing"))}),
        config({"a": call("year", column("target"))}, target={"naive": "utc"}),
        config(
            {"a": call("cyclic_sin", call("day_of_year", column("date")))}, date={"naive": "utc"}
        ),
    ]
    for definition in bad:
        with pytest.raises(ValueError):
            validate_temporal(TemporalConfig.model_validate(definition), source, "target")
    duplicate = config({"a": call("year", column("date"))}, date={"naive": "utc"})
    duplicate["features"] *= 2
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        TemporalConfig.model_validate(duplicate)


def test_shared_task_compilation_training_and_standalone_parity(tmp_path):
    from mlstudio.codegen.dispatch import generate_for_version, resolve_for_version
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.source import describe_columns
    from mlstudio.temporal_runtime_v1 import TemporalFeatures

    frame = pd.DataFrame(
        {"date": [f"2024-{1 + i % 12:02d}-15" for i in range(36)], "target": ["a", "b", "c"] * 12}
    )
    temporal = config({"month": call("month", column("date"))}, date={"naive": "utc"})
    for task, version, model in [
        ("binary_classification", "0.1", "logistic_regression"),
        ("regression", "0.2", "ridge"),
        ("multiclass_classification", "0.3", "logistic_regression"),
    ]:
        current = frame.copy()
        current["target"] = (
            list(range(36))
            if task == "regression"
            else (["a", "b"] * 18 if version == "0.1" else frame["target"])
        )
        dataset = SimpleNamespace(
            id="test",
            fingerprint="sha256:" + "a" * 64,
            size_bytes=100,
            columns=describe_columns(current),
        )
        payload = {
            "ir_version": version,
            "dataset": {"dataset_id": "test", "fingerprint": dataset.fingerprint},
            "target": {"column": "target"},
            "temporal": temporal,
            "features": {
                "date": {"included": False, "operations": []},
                "month": {"included": True, "operations": []},
            },
            "model": {"type": model},
            "split": {},
        }
        if version == "0.1":
            payload["target"]["positive_class"] = {"value_type": "string", "value": "b"}
        else:
            payload["task"] = task
        ir = load_ir(payload, task)
        plan, issues = resolve_for_version(ir, dataset, "target", current)
        assert plan is not None, issues
        source = generate_for_version(plan)
        path = tmp_path / f"generated_{version.replace('.', '_')}.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = TemporalFeatures(temporal).fit_transform(current[["date"]])
        actual = module.TemporalFeatures(temporal).fit_transform(current[["date"]])
        pd.testing.assert_frame_equal(expected, actual)
        assert "('temporal', TemporalFeatures(" in source
    # Real fitting and persistence without introducing another training path.
    import joblib
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline

    fitted = Pipeline(
        [
            ("temporal", TemporalFeatures(temporal)),
            (
                "select",
                ColumnTransformer([("month", "passthrough", ["month"])]),
            ),
            ("model", Ridge()),
        ]
    )
    fitted.fit(frame[["date"]], np.arange(36))
    artifact = tmp_path / "model.joblib"
    joblib.dump(fitted, artifact)
    np.testing.assert_allclose(
        fitted.predict(frame[["date"]]), joblib.load(artifact).predict(frame[["date"]])
    )


def test_temporal_preview_persistence_and_real_generated_execution(client, settings, tmp_path):
    from test_projects_datasets import configure, create, upload

    project = create(client)
    raw = (
        "date,label\n"
        + "\n".join(f"2024-{1 + i % 12:02d}-15,{'yes' if i % 2 else 'no'}" for i in range(36))
        + "\n"
    )
    dataset = upload(client, project, raw.encode()).json()
    assert configure(client, project, target_column="label").status_code == 200
    path = f"/api/v1/projects/{project['id']}"
    state = client.get(path + "/pipeline").json()
    ir = state["ir"]
    ir["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
    ir["features"] = {
        "date": {"included": False, "operations": []},
        "month": {"included": True, "operations": []},
    }
    ir["temporal"] = config({"month": call("month", column("date"))}, date={"naive": "utc"})
    ir["model"], ir["split"] = {"type": "logistic_regression"}, {}
    body = {"revision": state["revision"], "ir": ir}
    preview = client.post(path + "/pipeline/temporal-preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["columns"][0]["values"] == [float(1 + i % 12) for i in range(20)]
    assert client.get(path + "/pipeline").json()["revision"] == state["revision"]
    saved = client.patch(path + "/pipeline", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["code_generation_ready"], saved.json()["issues"]
    assert client.get(path + "/pipeline").json()["ir"]["temporal"]["version"] == "temporal-v1"
    assert client.post(path + "/pipeline/temporal-preview", json=body).status_code == 409
    code = client.get(path + "/code").json()
    admitted = client.post(
        path + "/runs",
        json={
            "request_id": str(uuid4()),
            "expected_revision": code["revision"],
            "expected_source_sha256": code["source_sha256"],
            "expected_plan_sha256": code["plan_sha256"],
        },
    )
    assert admitted.status_code == 202, admitted.text
    run_id = admitted.json()["id"]
    deadline = time.monotonic() + 60
    while True:
        run = client.get(path + f"/runs/{run_id}").json()
        if run["state"] in {"SUCCEEDED", "FAILED"}:
            break
        assert time.monotonic() < deadline, "Temporal Run did not finish"
        time.sleep(0.1)
    assert run["state"] == "SUCCEEDED", run.get("failure")
    directory = settings.home / "projects" / project["id"] / "runs" / run_id
    assert (directory / "generated_run.py").read_text(encoding="utf-8") == code["source"]
    assert (
        settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    ).read_bytes() == raw.encode()
    # A fresh process loads the generated model via the frozen standalone source;
    # it does not import the backend transformation implementation.
    loader = tmp_path / "load.py"
    loader.write_text(
        "import importlib.util, sys, joblib, pandas as pd\n"
        "spec=importlib.util.spec_from_file_location('frozen_workload', sys.argv[1])\n"
        "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "data=pd.DataFrame({'date':['2024-12-15']})\n"
        "assert joblib.load(sys.argv[2]).predict(data).shape == (1,)\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            str(loader),
            str(directory / "generated_run.py"),
            str(directory / "model.joblib"),
        ],
        check=True,
        timeout=30,
    )
    draft = client.post(
        path + "/code-drafts",
        json={
            "revision": code["revision"],
            "source_sha256": code["source_sha256"],
            "plan_sha256": code["plan_sha256"],
        },
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["origin_ir"]["temporal"]["version"] == "temporal-v1"
    assert "TEMPORAL_CONFIG" in draft.json()["source"]
    assert client.get(path + f"/runs/{run_id}/code").json()["source"] == code["source"]


def test_generalized_compiler_all_tasks_and_raw_saved_inference(tmp_path):
    import hashlib
    import json

    from mlstudio.codegen.csv_runtime import parse_csv_bytes
    from mlstudio.codegen.dispatch import generate_for_version, resolve_for_version
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.derived import context
    from mlstudio.services.source import describe_columns

    for task, version, model in [
        ("binary_classification", "0.1", "logistic_regression"),
        ("regression", "0.2", "ridge"),
        ("multiclass_classification", "0.3", "logistic_regression"),
    ]:
        values = pd.DataFrame(
            {
                "revenue": np.arange(36) + 20.0,
                "cost": np.arange(36) / 2.0,
                "orders": [0.0, 2.0, 3.0] * 12,
                "segment": [" Premium ", "Basic", "Other"] * 12,
                "date": [f"2024-{1 + i % 12:02d}-15" for i in range(36)],
                "target": list(range(36))
                if version == "0.2"
                else ["no", "yes"] * 18
                if version == "0.1"
                else ["a", "b", "c"] * 12,
            }
        )
        raw = values.to_csv(index=False).encode()
        frame = parse_csv_bytes(raw)
        dataset = SimpleNamespace(
            id="derived-test",
            fingerprint="sha256:" + hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            columns=describe_columns(frame),
        )
        general = {
            "version": "derived-v1",
            "features": [
                {
                    "name": "margin",
                    "expression": call(
                        "safe_divide", {"kind": "reference", "name": "profit"}, column("orders")
                    ),
                },
                {
                    "name": "profit",
                    "expression": call("subtract", column("revenue"), column("cost")),
                },
                {
                    "name": "month_scaled",
                    "expression": call(
                        "safe_divide",
                        {"kind": "reference", "name": "month"},
                        {"kind": "literal", "value": 12},
                    ),
                },
                {"name": "clean", "expression": call("lower", call("trim", column("segment")))},
            ],
        }
        payload = {
            "ir_version": version,
            "dataset": {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint},
            "target": {"column": "target"},
            "temporal": config({"month": call("month", column("date"))}, date={"naive": "utc"}),
            "derived": general,
            "features": {
                name: {"included": False, "operations": []} for name in frame if name != "target"
            },
            "model": {"type": model},
            "split": {},
        }
        if version == "0.1":
            payload.pop("temporal")
            payload["derived"]["features"][2]["expression"] = call(
                "safe_divide", column("revenue"), {"kind": "literal", "value": 12}
            )
        payload["features"].update(
            {
                "month": {"included": False, "operations": []},
                "margin": {
                    "included": True,
                    "operations": [{"type": "impute", "strategy": "median"}],
                },
                "profit": {"included": False, "operations": []},
                "month_scaled": {"included": True, "operations": []},
                "clean": {
                    "included": True,
                    "operations": [{"type": "encode", "method": "one_hot"}],
                },
            }
        )
        if version == "0.1":
            payload["features"].pop("month")
            payload["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
        else:
            payload["task"] = task
        ir = load_ir(payload, task)
        plan, issues = resolve_for_version(ir, dataset, "target", frame)
        assert plan is not None, issues
        source = generate_for_version(plan)
        assert source == generate_for_version(plan)
        if plan.temporal is not None:
            assert source.index("('temporal', TemporalFeatures(") < source.index(
                "('derived', DerivedFeatures("
            )
        else:
            assert "TEMPORAL_CONFIG" not in source
        directory = tmp_path / version
        directory.mkdir()
        source_path, data_path = directory / "generated.py", directory / "source.csv"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        data_path.write_bytes(raw)
        result_path, model_path = directory / "result.json", directory / "model.joblib"
        subprocess.run(
            [
                sys.executable,
                str(source_path),
                "--dataset",
                str(data_path),
                "--result",
                str(result_path),
                "--model",
                str(model_path),
            ],
            check=True,
            timeout=40,
        )
        assert json.loads(result_path.read_text())["status"] == "success"
        spec = importlib.util.spec_from_file_location(
            "generated_derived_" + version.replace(".", "_"), source_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = context(ir, dataset, frame)[1]
        raw_inputs = frame.drop(columns="target")
        transformed = (
            module.TemporalFeatures(ir.temporal.model_dump(mode="json")).transform(raw_inputs)
            if ir.temporal
            else raw_inputs
        )
        actual = module.DerivedFeatures(plan.derived.model_dump(mode="json")).transform(transformed)
        pd.testing.assert_frame_equal(expected.drop(columns="target"), actual)
        loader = directory / "inference.py"
        loader.write_text(
            "import importlib.util, sys, joblib, pandas as pd\n"
            "spec=importlib.util.spec_from_file_location('frozen',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "model=joblib.load(sys.argv[2]); raw=pd.read_csv(sys.argv[3]).drop(columns='target')\n"
            "assert model.predict(raw).shape == (len(raw),)\n"
            "try: model.predict(raw.drop(columns='orders'))\n"
            "except ValueError: pass\n"
            "else: raise AssertionError('missing raw input accepted')\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(loader), str(source_path), str(model_path), str(data_path)],
            check=True,
            timeout=30,
        )


def test_advanced_imputation_compiles_all_tasks_and_saved_raw_inference(tmp_path):
    import hashlib
    import json

    from mlstudio.codegen.csv_runtime import parse_csv_bytes
    from mlstudio.codegen.dispatch import generate_for_version, resolve_for_version
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.source import describe_columns

    for task, version, model in [
        ("binary_classification", "0.1", "logistic_regression"),
        ("regression", "0.2", "ridge"),
        ("multiclass_classification", "0.3", "logistic_regression"),
    ]:
        values = pd.DataFrame(
            {
                "income": [None if i % 3 == 0 else float(100 + i) for i in range(36)],
                "city": ["Pune", "Mumbai", None] * 12,
                "employment": ["Salaried", "Self"] * 18,
                "date": [None if i % 5 == 0 else f"2024-{1 + i % 12:02d}-15" for i in range(36)],
                "target": list(range(36))
                if version == "0.2"
                else ["no", "yes"] * 18
                if version == "0.1"
                else ["a", "b", "c"] * 12,
            }
        )
        raw = values.to_csv(index=False).encode()
        frame = parse_csv_bytes(raw)
        dataset = SimpleNamespace(
            id="advanced-test",
            fingerprint="sha256:" + hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            columns=describe_columns(frame),
        )
        generalized = {
            "version": "derived-v1",
            "features": [
                {
                    "name": "tenure",
                    "expression": call(
                        "safe_divide",
                        {"kind": "reference", "name": "month"},
                        {"kind": "literal", "value": 12},
                    ),
                },
                {
                    "name": "is_salary",
                    "expression": call(
                        "equal", column("employment"), {"kind": "literal", "value": "Salaried"}
                    ),
                },
                {"name": "clean_city", "expression": call("trim", column("city"))},
            ],
        }
        payload = {
            "ir_version": version,
            "dataset": {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint},
            "target": {"column": "target"},
            "temporal": config({"month": call("month", column("date"))}, date={"naive": "utc"}),
            "derived": generalized,
            "features": {
                name: {"included": False, "operations": []}
                for name in [*frame.columns, "month", "tenure", "is_salary", "clean_city"]
                if name != "target"
            },
            "imputation": {
                "version": "imputation-v1",
                "columns": {
                    "income": {
                        "rules": [
                            {
                                "condition": {"kind": "reference", "name": "is_salary"},
                                "strategy": "median",
                                "group_by": ["clean_city"],
                            }
                        ],
                        "fallback": {"strategy": "constant", "value": 99},
                        "indicator": "income_missing",
                    },
                    "tenure": {
                        "rules": [{"strategy": "mean", "group_by": ["clean_city"]}],
                        "fallback": {"strategy": "constant", "value": 0},
                        "indicator": "tenure_missing",
                    },
                },
            },
            "model": {"type": model},
            "split": {},
        }
        payload["features"]["income"] = {
            "included": True,
            "operations": [{"type": "scale", "method": "robust"}],
        }
        payload["features"]["tenure"]["included"] = True
        if version == "0.1":
            payload["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
        else:
            payload["task"] = task
        if version == "0.1":
            payload.pop("temporal")
            payload.pop("derived")
            for name in ["month", "tenure", "is_salary", "clean_city"]:
                payload["features"].pop(name)
            payload["imputation"]["columns"].pop("tenure")
            first_rule = payload["imputation"]["columns"]["income"]["rules"][0]
            first_rule["condition"] = call(
                "equal", column("employment"), {"kind": "literal", "value": "Salaried"}
            )
            first_rule["group_by"] = ["city"]
        ir = load_ir(json.loads(json.dumps(payload)), task)
        plan, issues = resolve_for_version(ir, dataset, "target", frame)
        assert plan is not None, issues
        expected_indicators = (
            ["income_missing"] if version == "0.1" else ["income_missing", "tenure_missing"]
        )
        assert [f.name for f in plan.features][-len(expected_indicators) :] == expected_indicators
        source = generate_for_version(plan)
        assert source == generate_for_version(plan)
        if version != "0.1":
            assert source.index("('derived', DerivedFeatures(") < source.index(
                "('advanced_imputation', ImputationFeatures("
            )
        directory = tmp_path / version
        directory.mkdir()
        source_path, data_path = directory / "generated.py", directory / "source.csv"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        data_path.write_bytes(raw)
        result_path, model_path = directory / "result.json", directory / "model.joblib"
        subprocess.run(
            [
                sys.executable,
                str(source_path),
                "--dataset",
                str(data_path),
                "--result",
                str(result_path),
                "--model",
                str(model_path),
            ],
            check=True,
            timeout=40,
        )
        assert json.loads(result_path.read_text())["status"] == "success"
        loader = directory / "load.py"
        loader.write_text(
            "import importlib.util,sys,joblib,pandas as pd,numpy as np\n"
            "spec=importlib.util.spec_from_file_location('frozen',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
            "model=joblib.load(sys.argv[2]);raw=pd.read_csv(sys.argv[3]).drop(columns='target')\n"
            "assert model.predict(raw).shape == (len(raw),)\n"
            "new=raw.iloc[:1].copy();new['city']='Unseen';new['income']=np.nan\n"
            "assert model.predict(new).shape == (1,)\n"
            "idx=list(model.named_steps).index('advanced_imputation')\n"
            "rowwise=model[:idx].transform(raw) if idx else raw\n"
            "transformed=model.named_steps['advanced_imputation'].transform(rowwise)\n"
            "assert transformed['income'].notna().all()\n"
            "np.testing.assert_allclose(transformed['income_missing'],raw['income'].isna().astype(float))\n"
            "np.testing.assert_allclose(transformed.loc[raw.income.notna(),'income'],raw.loc[raw.income.notna(),'income'])\n"
            "try:model.predict(raw.drop(columns='employment'))\n"
            "except ValueError:pass\n"
            "else:raise AssertionError('missing condition input accepted')\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(loader), str(source_path), str(model_path), str(data_path)],
            check=True,
            timeout=30,
        )
