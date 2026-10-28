"""Four focused Code Mode reporting scenarios, through real managed execution."""

from uuid import uuid4

import pytest
from test_code_runs import finished, submit
from test_regression_runs import ready_regression
from test_runs import ready


def enter_generated(client, setup):
    project, _, _, _, preview = setup(client)
    base = f"/api/v1/projects/{project['id']}"
    response = client.post(
        base + "/code-drafts",
        json={
            "revision": preview["revision"],
            "source_sha256": preview["source_sha256"],
            "plan_sha256": preview["plan_sha256"],
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    return base, draft, preview


def execute(client, path, draft, source):
    response = client.post(
        path,
        json={
            "draft_id": draft["id"],
            "revision": draft["revision"],
            "source": source,
            "request_id": str(uuid4()),
        },
    )
    assert response.status_code == 202, response.text
    run = finished(client, path, response.json()["id"])
    assert run["status"] == "COMPLETED", (run, client.get(f"{path}/{run['id']}/logs").json())
    evidence = client.get(f"{path}/{run['id']}/evaluation")
    assert evidence.status_code == 200, evidence.text
    return run, evidence.json()


def test_classification_reporting_reuses_typed_matrix_and_metrics(client, settings):
    settings.code_execution_enabled = True
    base, draft, preview = enter_generated(client, ready)
    assert "report_classification(" in draft["source"]
    assert "report_classification(" not in preview["source"]
    source = draft["source"].replace("predictions", "renamed_predictions")
    run, evidence = execute(client, base + "/code-runs", draft, source)
    assert evidence["status"] == "available"
    result = evidence["report"]["evaluation"]
    assert result["task"] == "binary_classification"
    assert result["confusion_matrix"]["labels"][1] == {"value_type": "string", "value": "yes"}
    assert sum(map(sum, result["confusion_matrix"]["values"])) == result["population"]["test"]
    assert 0 <= result["metrics"]["accuracy"] <= 1
    assert run["configuration"]["reporting"]["schema_version"] == "mlstudio-code-report-v1"
    assert client.get(base + "/runs").json()["total"] == 0


def test_regression_reporting_custom_values_and_input_validation(client, settings):
    settings.code_execution_enabled = True
    base, draft, _ = enter_generated(client, ready_regression)
    assert "report_regression(" in draft["source"]
    source = draft["source"].replace(
        "        result = {",
        """        from mlstudio_runtime import report_metric, report_output
        report_metric('zero', 0)
        report_output('features', ['x'])
        result = {""",
    )
    _, evidence = execute(client, base + "/code-runs", draft, source)
    result = evidence["report"]["evaluation"]
    assert result["task"] == "regression" and result["metrics"]["rmse"] >= 0
    assert evidence["report"]["metrics"] == {"zero": 0}
    assert evidence["report"]["outputs"] == {"features": ["x"]}
    from mlstudio import code_runtime as runtime

    for actual, predicted in [([[1]], [1]), ([float("nan")], [1]), ([1], [1, 2]), ([True], [1])]:
        with pytest.raises(ValueError):
            runtime.report_regression(y_true=actual, y_pred=predicted)
    with pytest.raises(ValueError):
        runtime.report_classification(y_true=[0, 2], y_pred=[0, 1], labels=[0, 1])


def test_absent_invalid_and_incompatible_evidence_never_becomes_charts(client, settings):
    settings.code_execution_enabled = True
    project, draft, path, _ = submit(client, "")
    for source, expected in [
        ("print('no reporting')", "not_reported"),
        ("from pathlib import Path\nPath('code-evaluation.json').write_text('{bad')", "invalid"),
        (
            "from mlstudio_runtime import report_classification\n"
            "report_classification(y_true=[0,1], y_pred=[0,1], labels=[0,1])",
            "invalid",
        ),
    ]:
        _, evidence = execute(client, path, draft, source)
        assert evidence["status"] == expected and evidence["report"] is None
        draft = client.get(f"/api/v1/projects/{project['id']}/code-drafts/active").json()


def test_historical_report_frozen_and_tampering_detected(client, settings):
    settings.code_execution_enabled = True
    project, draft, path, _ = submit(client, "")
    source = (
        "from mlstudio_runtime import report_regression\n"
        "report_regression(y_true=[1,2], y_pred=[1,2])"
    )
    run, original = execute(client, path, draft, source)
    draft = client.get(f"/api/v1/projects/{project['id']}/code-drafts/active").json()
    execute(client, path, draft, source.replace("y_pred=[1,2]", "y_pred=[2,1]"))
    assert client.get(f"{path}/{run['id']}/evaluation").json() == original
    artifact = settings.home / run["artifact_directory"] / "evaluation.json"
    artifact.write_text("{}", encoding="utf-8")
    changed = client.get(f"{path}/{run['id']}/evaluation").json()
    assert changed["status"] == "unavailable_or_corrupt" and changed["report"] is None
