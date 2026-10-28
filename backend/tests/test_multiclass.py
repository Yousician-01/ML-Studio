"""Focused multiclass contracts across current metadata, visual and Code execution."""

from uuid import uuid4

import pandas as pd
import pytest
from test_code_evaluation import execute as execute_code
from test_projects_datasets import configure, upload
from test_runs import terminal
from test_tracking import joined

from mlstudio import code_runtime
from mlstudio.services.source import DomainError
from mlstudio.services.task_policies import validate_target_for_task


def ready_multiclass(client, model="decision_tree"):
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Three classes",
            "problem_statement": "Predict category",
            "ml_objective": "multiclass_classification",
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    data = "x,target\n" + "".join(f"{i},{['amber', 'blue', 'cyan'][i % 3]}\n" for i in range(60))
    assert upload(client, project, data.encode()).status_code == 201
    response = configure(
        client, project, target_column="target", semantic_overrides={"x": "continuous"}
    )
    assert response.status_code == 200, response.text
    base = f"/api/v1/projects/{project['id']}"
    state = client.get(base + "/pipeline").json()
    ir = state["ir"]
    ir["model"] = {"type": model}
    ir["split"] = {"test_size": 0.25, "random_seed": 42, "stratify": True}
    state = client.patch(base + "/pipeline", json={"revision": state["revision"], "ir": ir})
    assert state.status_code == 200, state.text
    assert state.json()["configuration_ready"], state.json()["issues"]
    preview = client.get(base + "/code").json()
    assert preview["ready"], preview
    return base, state.json(), preview


def test_multiclass_target_and_split_validation(client):
    base, state, _ = ready_multiclass(client)
    assert [c["value"] for c in state["target_classes"]] == ["amber", "blue", "cyan"]
    for values in ([1.0, 1.5, 2.3], ["a", "b", None], [0, 1, 2], ["a", 2, "b"], [True, False]):
        with pytest.raises(DomainError):
            validate_target_for_task(pd.DataFrame({"y": values}), "y", "multiclass_classification")
    assert validate_target_for_task(
        pd.DataFrame({"y": [2, 0, 1]}),
        "y",
        "multiclass_classification",
        semantic_type="categorical",
    ) == [0, 1, 2]
    current = client.get(base + "/pipeline").json()
    current["ir"]["split"]["test_size"] = 0.05
    current["ir"]["model"] = {"type": "logistic_regression", "parameters": {"penalty": "l1"}}
    updated = client.patch(
        base + "/pipeline", json={"revision": current["revision"], "ir": current["ir"]}
    ).json()
    assert any(issue["code"] == "model_multiclass_penalty" for issue in updated["issues"])
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.train_validation import train_issues

    ir = load_ir(state["ir"], "multiclass_classification")
    assert any(
        i.severity == "blocking"
        for i in train_issues(ir, pd.Series(["a"] * 20 + ["b"] * 2 + ["c"]))
    )


def test_multiclass_visual_training_and_immutable_result(client):
    for model in ("decision_tree", "random_forest", "logistic_regression"):
        base, _, preview = ready_multiclass(client, model)
        started = client.post(
            base + "/runs",
            json={
                "request_id": str(uuid4()),
                "expected_revision": preview["revision"],
                "expected_source_sha256": preview["source_sha256"],
                "expected_plan_sha256": preview["plan_sha256"],
            },
        )
        assert started.status_code == 202, started.text
        run = terminal(client, base + "/runs", started.json()["id"])
        assert run["state"] == "SUCCEEDED", run
        joined(client)
        result = client.get(base + "/runs/" + run["id"]).json()["result"]
        assert result["schema_version"] == "mlstudio-result-v3"
        assert result["task"] == "multiclass_classification"
        assert len(result["confusion_matrix"]["labels"]) == len(result["per_class"]) == 3
        assert sum(row["support"] for row in result["per_class"]) == result["population"]["test"]
        assert set(result["metrics"]) == {
            "accuracy",
            "precision_macro",
            "recall_macro",
            "f1_macro",
            "precision_weighted",
            "recall_weighted",
            "f1_weighted",
        }
        assert "positive_class" not in run["summary"]["target"]
        assert client.get(base + "/code").json()["source"] == preview["source"]


def test_multiclass_generated_code_mode_reports(client, settings):
    settings.code_execution_enabled = True
    base, state, preview = ready_multiclass(client)
    assert client.get(base + "/code").json()["source_sha256"] == preview["source_sha256"]
    draft = client.post(
        base + "/code-drafts",
        json={
            "revision": preview["revision"],
            "source_sha256": preview["source_sha256"],
            "plan_sha256": preview["plan_sha256"],
        },
    ).json()
    assert "report_classification(" in draft["source"]
    run, evidence = execute_code(
        client,
        base + "/code-runs",
        draft,
        draft["source"].replace("predictions", "renamed_predictions"),
    )
    assert evidence["status"] == "available"
    assert evidence["report"]["schema_version"] == "mlstudio-code-report-v2"
    result = evidence["report"]["evaluation"]
    assert (
        result["task"] == "multiclass_classification"
        and len(result["confusion_matrix"]["values"]) == 3
    )
    assert run["configuration"]["reporting"]["task"] == state["ir"]["task"]


def test_multiclass_reporting_bounds_consistency_and_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("MLSTUDIO_EVALUATION_PATH", str(tmp_path / "report.json"))
    code_runtime.report_classification(y_true=[0, 1, 2, 0], y_pred=[0, 2, 2, 1], labels=[0, 1, 2])
    from mlstudio.execution.artifacts import strict_json

    report = strict_json((tmp_path / "report.json").read_bytes())
    code_runtime.validate_report(report, "multiclass_classification")
    with pytest.raises(ValueError):
        code_runtime.validate_report(report, "binary_classification")
    report["evaluation"]["per_class"][0]["label"]["value"] = False
    with pytest.raises(ValueError):
        code_runtime.validate_report(report, "multiclass_classification")
    report["evaluation"]["per_class"][0]["label"]["value"] = 0
    report["evaluation"]["confusion_matrix"]["values"][0][0] += 1
    with pytest.raises(ValueError):
        code_runtime.validate_report(report, "multiclass_classification")
    for actual, predicted, labels in [
        ([0, 1, 3], [0, 1, 2], [0, 1, 2]),
        ([[0], [1], [2]], [0, 1, 2], [0, 1, 2]),
        (["a", 1, "b"], ["a", 1, "b"], ["a", 1, "b"]),
        ([0, 1, 2], [0, 1, 2], list(range(51))),
    ]:
        with pytest.raises(ValueError):
            code_runtime.report_classification(y_true=actual, y_pred=predicted, labels=labels)
    code_runtime.report_classification(
        y_true=[False, True], y_pred=[False, False], labels=[False, True]
    )
    legacy = strict_json((tmp_path / "report.json").read_bytes())
    assert legacy["schema_version"] == "mlstudio-code-report-v1"
    code_runtime.validate_report(legacy, "binary_classification")
