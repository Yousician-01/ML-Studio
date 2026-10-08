"""Real local MLflow store tests: association, frozen inputs, and failure isolation."""

import json
from pathlib import Path

import joblib
import pytest
from alembic.config import Config
from test_projects_datasets import upload
from test_runs import Exited, fake_launch, ready, terminal
from test_train_configuration import save

from alembic import command
from mlstudio.execution import tracking
from mlstudio.models import Run


def joined(client):
    for worker in client.app.state.execution.workers:
        worker.join(timeout=45)
        assert not worker.is_alive()


def test_local_success_tracking_and_frozen_history(client, settings, monkeypatch, tmp_path):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://invalid.example/private")
    monkeypatch.setenv("MLFLOW_REGISTRY_URI", "https://invalid.example/private")
    monkeypatch.setenv("_MLFLOW_SERVER_ARTIFACT_ROOT", "s3://not-authorized")
    project, dataset, url, body, preview = ready(client)
    response = client.post(url, json=body)
    assert response.status_code == 202
    run = terminal(client, url, response.json()["id"])
    joined(client)
    run = client.get(f"{url}/{run['id']}").json()
    assert run["state"] == "SUCCEEDED"
    assert run["tracking_status"] == "SYNCHRONIZED", run
    ml = tracking.client_for(settings)
    external = ml.get_run(run["mlflow_run_id"])
    assert external.info.status == "FINISHED"
    assert external.data.metrics == run["result"]["metrics"]
    assert external.data.tags["mlstudio.run_id"] == run["id"]
    assert external.data.tags["mlstudio.dataset_fingerprint"] == dataset["fingerprint"]
    assert external.data.params["model"] == run["summary"]["model"]["name"]
    names = {item.path for item in ml.list_artifacts(external.info.run_id)}
    assert names == {
        "pipeline_ir.json",
        "execution_plan.json",
        "package.json",
        "generated_run.py",
        "result.json",
        "model_reference.json",
    }
    assert (settings.home / "mlflow/mlflow.db").is_file()
    assert not (tmp_path / "mlruns").exists()
    assert external.info.artifact_uri.startswith((settings.home / "mlflow/artifacts").as_uri())
    code = ml.download_artifacts(external.info.run_id, "generated_run.py")
    assert Path(code).read_bytes() == preview["source"].encode()
    reference = json.loads(
        Path(ml.download_artifacts(external.info.run_id, "model_reference.json")).read_text()
    )
    assert reference["sha256"] == run["artifacts"]["model.joblib"]["sha256"]
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["model"]["parameters"]["C"] = 9
    assert save(client, path, state).status_code == 200
    assert upload(client, project, expected=dataset["id"]).status_code == 201
    historical = client.get(f"{url}/{run['id']}").json()
    assert historical["pipeline_ir"] == run["pipeline_ir"]
    assert historical["execution_plan"] == run["execution_plan"]
    assert (
        client.get(url, params={"request_id": body["request_id"]}).json()["items"][0]["id"]
        == run["id"]
    )
    assert client.get(f"{url}/capacity").json()["occupied"] is False


def test_tracking_failure_and_idempotent_reconcile(client, settings, monkeypatch):
    fake_launch(monkeypatch, lambda *_: Exited(1))
    original = tracking.client_for
    monkeypatch.setattr(tracking, "client_for", lambda _: (_ for _ in ()).throw(OSError("secret")))
    _, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    joined(client)
    failed = client.get(f"{url}/{run['id']}").json()
    assert failed["tracking_status"] == "FAILED"
    assert "secret" not in json.dumps(failed)
    assert failed["failure"] == run["failure"] and failed["result"] is None
    monkeypatch.setattr(tracking, "client_for", original)
    sessions = client.app.state.session_factory
    tracking.reconcile(settings, sessions)
    repaired = client.get(f"{url}/{run['id']}").json()
    assert repaired["tracking_status"] == "SYNCHRONIZED"
    ml = original(settings)
    external = ml.get_run(repaired["mlflow_run_id"])
    assert external.info.status == "FAILED"
    assert external.data.metrics == {}
    assert {a.path for a in ml.list_artifacts(external.info.run_id)} == {
        "pipeline_ir.json",
        "execution_plan.json",
        "package.json",
        "generated_run.py",
    }
    with sessions() as session:
        session.get(Run, run["id"]).tracking_status = "FAILED"
        session.commit()
    tracking.reconcile(settings, sessions)
    matches = ml.search_runs(
        [external.info.experiment_id], filter_string=f"tags.`mlstudio.run_id` = '{run['id']}'"
    )
    assert len(matches) == 1
    assert client.get(f"{url}/{run['id']}").json()["mlflow_run_id"] == external.info.run_id


def test_reconcile_finds_created_external_run_after_association_write_failure(
    client, settings, monkeypatch
):
    fake_launch(monkeypatch, lambda *_: Exited(1))
    original = tracking.update

    def fail_association(sessions, run_id, **values):
        if "mlflow_run_id" in values:
            raise OSError("Simulated lost local association commit")
        return original(sessions, run_id, **values)

    monkeypatch.setattr(tracking, "update", fail_association)
    _, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    joined(client)
    assert client.get(f"{url}/{run['id']}").json()["mlflow_run_id"] is None
    monkeypatch.setattr(tracking, "update", original)
    tracking.reconcile(settings, client.app.state.session_factory)
    repaired = client.get(f"{url}/{run['id']}").json()
    assert repaired["tracking_status"] == "SYNCHRONIZED"
    ml = tracking.client_for(settings)
    external = ml.get_run(repaired["mlflow_run_id"])
    assert len(ml.search_runs([external.info.experiment_id])) == 1


def test_success_remains_success_when_tracking_fails(client, settings, monkeypatch):
    original = tracking.client_for
    monkeypatch.setattr(tracking, "client_for", lambda _: (_ for _ in ()).throw(OSError("secret")))
    _, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    joined(client)
    before = client.get(f"{url}/{run['id']}").json()
    assert before["state"] == "SUCCEEDED" and before["tracking_status"] == "FAILED"
    monkeypatch.setattr(tracking, "client_for", original)

    def forbidden(*args, **kwargs):
        raise AssertionError("Tracking must neither load a model nor launch training")

    monkeypatch.setattr(joblib, "load", forbidden)
    from mlstudio.execution import process

    monkeypatch.setattr(process, "launch", forbidden)
    tracking.reconcile(settings, client.app.state.session_factory)
    after = client.get(f"{url}/{run['id']}").json()
    assert after["tracking_status"] == "SYNCHRONIZED"
    for key in ("state", "result", "artifacts", "pipeline_ir", "execution_plan", "finished_at"):
        assert after[key] == before[key]


@pytest.mark.parametrize(
    "uri", ["s3://remote/bucket", "https://remote/artifacts", "file:///outside"]
)
def test_reject_redirected_artifacts(settings, uri):
    with pytest.raises(ValueError):
        tracking.local_artifact_location(settings.home, uri)


def test_tracking_migration_from_phase6a(settings):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    command.upgrade(config, "0004_runs")
    command.upgrade(config, "head")
    command.current(config, check_heads=True)
    command.check(config)


def test_unavailable_auc_is_not_logged_as_zero(client, settings):
    project, _, url, body, _ = ready(client)
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["split"].update(test_size=0.05, stratify=False)
    assert save(client, path, state).status_code == 200
    preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
    assert preview["ready"]
    assert "mlflow" not in preview["source"].lower()
    body.update(
        expected_revision=preview["revision"],
        expected_source_sha256=preview["source_sha256"],
        expected_plan_sha256=preview["plan_sha256"],
    )
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    joined(client)
    run = client.get(f"{url}/{run['id']}").json()
    assert run["state"] == "SUCCEEDED" and run["tracking_status"] == "SYNCHRONIZED"
    assert run["result"]["population"]["test"] == 1
    assert run["result"]["metrics"]["roc_auc"] is None
    ml = tracking.client_for(settings)
    assert set(ml.get_run(run["mlflow_run_id"]).data.metrics) == {
        "accuracy",
        "precision",
        "recall",
        "f1",
    }
