"""Regression through public preview, immutable admission and the shared executor."""

import json
from uuid import uuid4

import joblib
import pytest
from fastapi.testclient import TestClient
from regression_fixtures import prepared
from scipy import sparse
from test_projects_datasets import configure, upload
from test_regression_configuration import save
from test_runs import terminal
from test_task_targets import regression
from test_tracking import joined

from mlstudio.execution import tracking
from mlstudio.execution.artifacts import digest
from mlstudio.main import create_app


def ready_regression(client, model="linear_regression", *, mixed=False, data=None, fraction=0.2):
    ir, _, _, data = prepared(model, mixed=mixed, data=data, fraction=fraction)
    project = regression(client)
    uploaded = upload(client, project, data)
    assert uploaded.status_code == 201, uploaded.text
    dataset = uploaded.json()
    semantics = {"x": "continuous", **({"city": "categorical"} if mixed else {})}
    configured = configure(client, project, target_column="y", semantic_overrides=semantics)
    assert configured.status_code == 200, configured.text
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    payload = ir.model_dump(mode="json")
    payload["dataset"] = state["ir"]["dataset"]
    state["ir"] = payload
    saved = save(client, path, state)
    assert saved.status_code == 200, saved.text
    preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
    assert preview["ready"], preview
    assert preview["generator"] == "mlstudio-python-v2"
    body = {
        "request_id": str(uuid4()),
        "expected_revision": preview["revision"],
        "expected_source_sha256": preview["source_sha256"],
        "expected_plan_sha256": preview["plan_sha256"],
    }
    return project, dataset, f"/api/v1/projects/{project['id']}/runs", body, preview


def execute(client, url, body):
    response = client.post(url, json=body)
    assert response.status_code == 202, response.text
    run = terminal(client, url, response.json()["id"])
    joined(client)
    return client.get(f"{url}/{run['id']}").json()


@pytest.mark.parametrize("model", ["linear_regression", "ridge"])
@pytest.mark.parametrize("mixed", [False, True])
def test_real_regression_run_and_tracking(client, settings, model, mixed):
    project, dataset, url, body, preview = ready_regression(client, model, mixed=mixed)
    run = execute(client, url, body)
    assert run["state"] == "SUCCEEDED", run
    assert run["tracking_status"] == "SYNCHRONIZED", run
    plan, result = run["execution_plan"], run["result"]
    assert run["summary"]["task"] == result["task"] == "regression"
    assert run["summary"]["result_schema"] == result["schema_version"] == "mlstudio-result-v2"
    assert run["provenance"]["task"] == "regression"
    assert result["source_sha256"] == body["expected_source_sha256"]
    assert result["plan_sha256"] == body["expected_plan_sha256"]
    assert result["dataset"]["fingerprint"] == dataset["fingerprint"]
    assert set(result["metrics"]) == {"mae", "mse", "rmse", "r2"}
    assert "positive_class" not in result and "confusion_matrix" not in result
    directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
    assert (directory / "generated_run.py").read_bytes() == preview["source"].encode()
    assert digest((directory / "execution_plan.json").read_bytes()) == body["expected_plan_sha256"]
    evidence = json.loads((directory / "execution.json").read_bytes())
    assert evidence["arguments"][6] == str(directory / "generated_run.py")
    fitted = joblib.load(directory / "model.joblib")  # Only our trusted test-produced model.
    _, _, frame, _ = prepared(model, mixed=mixed)
    transformed = fitted["preprocessor"].transform(frame[[f["name"] for f in plan["features"]]])
    assert sparse.issparse(transformed) is mixed
    assert type(fitted["model"]).__name__ == plan["model"]["estimator"]
    external = tracking.client_for(settings).get_run(run["mlflow_run_id"])
    assert external.data.tags["mlstudio.task"] == "regression"
    assert external.data.params["model"] == plan["model"]["estimator"]
    assert "positive_class" not in external.data.params
    assert external.data.metrics == {k: v for k, v in result["metrics"].items() if v is not None}
    # Idempotency survives later mutable edits and replacement; old evidence does not change.
    state = client.get(f"/api/v1/projects/{project['id']}/pipeline").json()
    state["ir"]["model"]["parameters"]["fit_intercept"] = False
    assert save(client, f"/api/v1/projects/{project['id']}/pipeline", state).status_code == 200
    assert upload(client, project, expected=dataset["id"]).status_code == 201
    assert client.post(url, json=body).json()["id"] == run["id"]
    assert client.get(f"{url}/{run['id']}/code").json()["source"] == preview["source"]
    after = client.get(f"{url}/{run['id']}").json()
    for key in ("summary", "result", "execution_plan", "pipeline_ir", "finished_at", "provenance"):
        assert after[key] == run[key]
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"{url}/{run['id']}").json()["result"] == result
    old_source = (
        settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    )
    old_source.unlink()
    retained = client.get(f"{url}/{run['id']}").json()
    assert retained["artifacts"]["dataset_source"]["integrity"] == "missing"
    assert retained["result"] == result
    assert client.get(f"{url}/{run['id']}/code").json()["source"] == preview["source"]


@pytest.mark.parametrize(
    "key", ["expected_revision", "expected_source_sha256", "expected_plan_sha256"]
)
def test_regression_stale_preview_creates_no_run(client, key):
    _, _, url, body, _ = ready_regression(client)
    body[key] = body[key] + 1 if key == "expected_revision" else "sha256:" + "0" * 64
    response = client.post(url, json=body)
    assert response.status_code == 409, response.text
    assert client.get(url).json()["total"] == 0


def test_regression_replacement_and_source_corruption_block_admission(client, settings):
    project, dataset, url, body, _ = ready_regression(client)
    source = settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    original = source.read_bytes()
    source.write_bytes(b"changed")
    assert client.post(url, json=body).status_code == 409
    assert not client.get(f"/api/v1/projects/{project['id']}/code").json()["ready"]
    source.write_bytes(original)
    assert upload(client, project, expected=dataset["id"]).status_code == 201
    assert client.post(url, json=body).status_code == 409
    preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
    assert not preview["ready"] and preview["source"] is None
    assert client.get(url).json()["total"] == 0


@pytest.mark.parametrize("case", ["constant", "tiny_missing", "negative"])
def test_regression_metric_edge_cases_and_tracking(client, settings, case):
    from sklearn.model_selection import train_test_split

    if case == "constant":
        data = ("x,y\n" + "\n".join(f"{i},0" for i in range(10))).encode()
    elif case == "tiny_missing":
        data = b"x,y\n1,1\n2,2\n3,1\n4,\n"
    else:
        _, held_out = train_test_split(list(range(20)), test_size=0.2, random_state=42)
        values = {row: 100 + i for i, row in enumerate(held_out)}
        data = ("x,y\n" + "\n".join(f"{i},{values.get(i, 0)}" for i in range(20))).encode()
    _, _, url, body, _ = ready_regression(client, data=data)
    run = execute(client, url, body)
    assert run["state"] == "SUCCEEDED" and run["tracking_status"] == "SYNCHRONIZED", run
    result = run["result"]
    logged = tracking.client_for(settings).get_run(run["mlflow_run_id"]).data.metrics
    if case == "negative":
        assert result["metrics"]["r2"] < 0 and logged["r2"] == result["metrics"]["r2"]
    else:
        assert result["metrics"]["r2"] is None and "r2" not in logged
        expected = "constant_test_target" if case == "constant" else "test_population_too_small"
        assert result["r2_unavailable_reason"] == expected
    if case == "constant":
        assert logged == {"mae": 0.0, "mse": 0.0, "rmse": 0.0}
    if case == "tiny_missing":
        assert result["population"] == {"source": 4, "eligible": 3, "training": 2, "test": 1}


def synthetic_result(directory):
    """Aggregate fixture for orchestration faults, not proof of model calculations."""
    from mlstudio.codegen.v2.schemas import RegressionPlan, evaluation_context, plan_sha256

    plan = RegressionPlan.model_validate_json((directory / "execution_plan.json").read_bytes())
    payload = plan.model_dump(mode="json")
    return {
        "schema_version": "mlstudio-result-v2",
        "task": "regression",
        "status": "success",
        "dataset": payload["dataset"],
        "source": payload["source"],
        "generator": plan.generator,
        "implementation_version": plan.implementation.version,
        "plan_sha256": plan_sha256(plan),
        "source_sha256": digest((directory / "generated_run.py").read_bytes()),
        "model": payload["model"],
        "evaluation": evaluation_context(plan),
        "metrics": {"mae": 0.0, "mse": 0.0, "rmse": 0.0, "r2": 1.0},
        "r2_unavailable_reason": None,
        "test_target_constant": False,
        "population": {"source": 20, "eligible": 20, "training": 16, "test": 4},
        "artifacts": {"model": {"kind": "complete_pipeline", "filename": "model.joblib"}},
        "versions": {"python": plan.implementation.python, **plan.implementation.libraries},
    }


@pytest.mark.parametrize(
    "mode,code",
    [
        ("protocol", "result_invalid"),
        ("source", "result_invalid"),
        ("plan", "result_invalid"),
        ("missing", "model_missing"),
        ("empty", "model_invalid"),
        ("oversized", "model_invalid"),
        ("failure", "nonzero_exit"),
        ("timeout", "timeout"),
    ],
)
def test_regression_failed_finalization(client, settings, monkeypatch, mode, code):
    from test_runs import Exited, fake_launch

    from mlstudio.execution import process
    from mlstudio.execution.results import ExecutionFailure

    settings.run_model_bytes = 10

    def launch(_args, directory):
        result = synthetic_result(directory)
        if mode == "protocol":
            result["schema_version"] = "unknown"
        elif mode == "source":
            result["source_sha256"] = "sha256:" + "0" * 64
        elif mode == "plan":
            result["plan_sha256"] = "sha256:" + "0" * 64
        elif mode == "failure":
            result = {
                "schema_version": "mlstudio-result-v2",
                "task": "regression",
                "status": "failed",
                "stage": "training",
                "message": "private row secret",
            }
        (directory / ".pending/result.json").write_text(json.dumps(result), encoding="utf-8")
        if mode != "missing":
            (directory / ".pending/model.joblib").write_bytes(
                b"" if mode == "empty" else b"x" * (11 if mode == "oversized" else 1)
            )
        return Exited(1 if mode == "failure" else 0)

    fake_launch(monkeypatch, launch)
    if mode == "timeout":

        def timed_out(*_):
            raise ExecutionFailure("timeout")

        monkeypatch.setattr(process, "wait", timed_out)
    _, _, url, body, _ = ready_regression(client)
    run = execute(client, url, body)
    assert run["state"] == "FAILED" and run["failure"]["code"] == code, run
    assert run["result"] is None and "model.joblib" not in run["artifacts"]
    if mode == "failure":
        assert run["failure"]["stage"] == "training"
        assert "private row secret" not in json.dumps(run)


def test_regression_tracking_failure_reconcile_and_unknown_history(client, settings, monkeypatch):
    from sqlalchemy import update
    from test_runs import Exited, fake_launch

    from mlstudio.models import Run

    def launch(_args, directory):
        (directory / ".pending/result.json").write_text(json.dumps(synthetic_result(directory)))
        (directory / ".pending/model.joblib").write_bytes(b"trusted-test-placeholder")
        return Exited()

    fake_launch(monkeypatch, launch)
    original = tracking.client_for
    monkeypatch.setattr(tracking, "client_for", lambda _: (_ for _ in ()).throw(OSError("private")))
    _, _, url, body, _ = ready_regression(client)
    before = execute(client, url, body)
    assert before["state"] == "SUCCEEDED" and before["tracking_status"] == "FAILED"
    monkeypatch.setattr(tracking, "client_for", original)
    monkeypatch.setattr(joblib, "load", lambda *_: pytest.fail("Never unpickle for tracking"))
    sessions = client.app.state.session_factory
    tracking.reconcile(settings, sessions)
    after = client.get(f"{url}/{before['id']}").json()
    assert after["tracking_status"] == "SYNCHRONIZED", after
    for key in (
        "state",
        "result",
        "artifacts",
        "summary",
        "pipeline_ir",
        "execution_plan",
        "finished_at",
    ):
        assert after[key] == before[key]
    tracking.reconcile(settings, sessions)
    ml = original(settings)
    external = ml.get_run(after["mlflow_run_id"])
    assert len(ml.search_runs([external.info.experiment_id])) == 1
    # Deliberate external SQLite corruption, bypassing the ORM terminal-write guard.
    bad = {**after["result"], "schema_version": "future-unsupported"}
    with sessions() as session:
        session.execute(update(Run).where(Run.id == after["id"]).values(result=bad))
        session.commit()
    unsupported = client.get(f"{url}/{after['id']}")
    assert unsupported.status_code == 200
    assert unsupported.json()["result"] is None
    assert "unsupported" in unsupported.json()["result_error"].lower()
    assert client.get(url).json()["items"][0]["result_error"]
    with sessions() as session:
        assert session.get(Run, after["id"]).result == bad  # Read never repairs history.


def test_regression_concurrency_idempotency_and_interrupted_recovery(client, settings, monkeypatch):
    import threading

    from test_runs import Exited, fake_launch

    entered, release = threading.Event(), threading.Event()

    def launch(*_):
        entered.set()
        assert release.wait(10)
        return Exited(1)

    fake_launch(monkeypatch, launch)
    project, _, url, body, _ = ready_regression(client)
    try:
        accepted = client.post(url, json=body).json()
        assert entered.wait(5)
        assert client.post(url, json=body).json()["id"] == accepted["id"]
        assert client.post(url, json={**body, "request_id": str(uuid4())}).status_code == 409
        with TestClient(create_app(settings)) as second:
            assert second.post(url, json={**body, "request_id": str(uuid4())}).status_code == 409
    finally:
        release.set()
    terminal(client, url, accepted["id"])
    joined(client)
    coordinator = client.app.state.execution
    monkeypatch.setattr(coordinator, "submit", lambda _, lease: coordinator.release(lease))
    body = {**body, "request_id": str(uuid4())}
    pending = client.post(url, json=body).json()
    assert pending["state"] == "CREATED"
    with TestClient(create_app(settings)) as restarted:
        recovered = restarted.get(f"{url}/{pending['id']}").json()
        assert recovered["state"] == "FAILED" and recovered["result"] is None
        assert recovered["failure"]["code"] == "execution_interrupted"
        assert recovered["summary"]["task"] == "regression"
        assert restarted.get(f"{url}/{pending['id']}/code").status_code == 200
        assert restarted.post(url, json=body).json()["id"] == pending["id"]
