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
