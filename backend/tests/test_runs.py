import io
import json
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_projects_datasets import upload
from test_train_configuration import experiment, save

from mlstudio.execution import process
from mlstudio.execution.artifacts import digest
from mlstudio.main import create_app


class Exited:
    """No child exists; only exercises orchestration failure paths."""

    pid = -1
    returncode = 0

    def __init__(self, code=0, output=b""):
        self.returncode = code
        self.stdout = io.BytesIO(output)
        self.stderr = io.BytesIO(output)

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode


def fake_launch(monkeypatch, callback):
    monkeypatch.setattr(process, "identity", lambda p: {"pid": -1, "created": None})
    monkeypatch.setattr(process, "launch", callback)


def ready(client, model="logistic_regression"):
    project, dataset, path, state = experiment(client)
    state["ir"]["model"] = {"type": model}
    saved = save(client, path, state)
    assert saved.status_code == 200, saved.text
    preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
    assert preview["ready"], preview
    body = {
        "request_id": str(uuid4()),
        "expected_revision": preview["revision"],
        "expected_source_sha256": preview["source_sha256"],
        "expected_plan_sha256": preview["plan_sha256"],
    }
    return project, dataset, f"/api/v1/projects/{project['id']}/runs", body, preview


def terminal(client, url, run_id):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        response = client.get(f"{url}/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["state"] in ("SUCCEEDED", "FAILED"):
            return run
        time.sleep(0.05)
    pytest.fail("Run did not reach a terminal state.")


@pytest.mark.parametrize("model", ["logistic_regression", "decision_tree", "random_forest"])
def test_real_run(client, settings, model):
    project, dataset, url, body, preview = ready(client, model)
    response = client.post(url, json=body)
    assert response.status_code == 202, response.text
    run = terminal(client, url, response.json()["id"])
    assert run["state"] == "SUCCEEDED", run
    directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
    assert (directory / "generated_run.py").read_bytes() == preview["source"].encode()
    assert digest((directory / "execution_plan.json").read_bytes()) == preview["plan_sha256"]
    evidence = json.loads((directory / "execution.json").read_bytes())
    assert evidence["arguments"][6] == str(directory / "generated_run.py")
    assert evidence["exit_code"] == 0
    assert run["result"]["confusion_matrix"]["labels"][1] == {
        "value_type": "string",
        "value": "yes",
    }
    assert client.post(url, json=body).json()["id"] == run["id"]
    assert client.get(f"{url}/{run['id']}/code").json()["source"] == preview["source"]
    assert client.get(url).json()["total"] == 1
    assert (
        client.get(f"/api/v1/projects/{project['id']}").json()["revision"]
        == body["expected_revision"]
    )


@pytest.mark.parametrize(
    "key", ["expected_revision", "expected_source_sha256", "expected_plan_sha256"]
)
def test_stale_no_run(client, key):
    _, _, url, body, _ = ready(client)
    body[key] = body[key] + 1 if key == "expected_revision" else "sha256:" + "0" * 64
    response = client.post(url, json=body)
    assert response.status_code == 409, response.text
    assert client.get(url).json()["total"] == 0


@pytest.mark.parametrize(
    "mode,code",
    [
        ("launch", "launch_failure"),
        ("exit", "nonzero_exit"),
        ("missing", "result_missing"),
        ("malformed", "result_invalid"),
        ("failed", "result_invalid"),
    ],
)
def test_execution_failures(client, monkeypatch, mode, code):
    def launch(args, directory):
        if mode == "launch":
            raise OSError("sensitive exception")
        if mode == "malformed":
            (directory / ".pending/result.json").write_bytes(b"{")
        if mode == "failed":
            (directory / ".pending/result.json").write_text('{"status":"failed"}')
        return Exited(1 if mode == "exit" else 0)

    fake_launch(monkeypatch, launch)
    _, _, url, body, _ = ready(client)
    response = client.post(url, json=body)
    assert response.status_code == 202
    run = terminal(client, url, response.json()["id"])
    assert run["state"] == "FAILED" and run["failure"]["code"] == code
    assert run["result"] is None and "model.joblib" not in run["artifacts"]
    assert (run["started_at"] is None) == (mode == "launch")
    assert "sensitive" not in json.dumps(run)


def test_sequence_idempotency_and_history(client, monkeypatch, settings):
    fake_launch(monkeypatch, lambda *_: Exited(1))
    project, dataset, url, body, preview = ready(client)
    first = client.post(url, json=body).json()
    terminal(client, url, first["id"])
    # No experiment revision is consumed by Run allocation.
    body2 = {**body, "request_id": str(uuid4())}
    second = client.post(url, json=body2).json()
    terminal(client, url, second["id"])
    assert (first["sequence"], second["sequence"]) == (1, 2)
    assert (
        client.post(
            url, json={**body, "expected_revision": body["expected_revision"] + 1}
        ).status_code
        == 409
    )
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["model"]["parameters"]["C"] = 4
    assert save(client, path, state).status_code == 200
    assert upload(client, project, expected=dataset["id"]).status_code == 201
    assert client.post(url, json=body).json()["id"] == first["id"]
    assert client.get(f"{url}/{first['id']}/code").json()["source"] == preview["source"]
    assert (
        settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    ).exists()
    historical = (
        settings.home / "projects" / project["id"] / "runs" / first["id"] / "generated_run.py"
    )
    historical.write_bytes(b"corrupt")
    assert client.get(f"{url}/{first['id']}/code").status_code == 409
    assert (
        client.get(f"{url}/{first['id']}").json()["artifacts"]["generated_run.py"]["integrity"]
        == "unavailable_or_corrupt"
    )


def test_active_capacity_and_deletion(client, monkeypatch, settings):
    entered, release = threading.Event(), threading.Event()

    def launch(*_):
        entered.set()
        assert release.wait(10)
        return Exited(1)

    fake_launch(monkeypatch, launch)
    project, _, url, body, _ = ready(client)
    try:
        response = client.post(url, json=body)
        assert response.status_code == 202
        assert entered.wait(5)
        assert client.post(url, json=body).json()["id"] == response.json()["id"]
        assert client.post(url, json={**body, "request_id": str(uuid4())}).status_code == 409
        deletion = f"/api/v1/projects/{project['id']}?revision={body['expected_revision']}"
        assert client.delete(deletion).status_code == 409
        with TestClient(create_app(settings)) as second:
            assert second.post(url, json={**body, "request_id": str(uuid4())}).status_code == 409
    finally:
        release.set()
    terminal(client, url, response.json()["id"])
    assert client.delete(deletion).status_code == 204
    assert not (settings.home / "projects" / project["id"]).exists()


def test_log_bounds(client, monkeypatch, settings):
    settings.run_log_bytes = 128
    fake_launch(monkeypatch, lambda *_: Exited(1, b"a" * 1000000))
    project, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
    for name in ("stdout.log", "stderr.log"):
        assert (directory / name).stat().st_size == 128
    evidence = json.loads((directory / "execution.json").read_bytes())
    assert all(item["truncated"] for item in evidence["logs"].values())


def test_recovery_created_and_orphan(client, monkeypatch, settings):
    coordinator = client.app.state.execution
    monkeypatch.setattr(coordinator, "submit", lambda run_id, lease: coordinator.release(lease))
    project, _, url, body, _ = ready(client)
    run = client.post(url, json=body).json()
    orphan = settings.home / "projects" / project["id"] / "runs" / str(uuid4())
    orphan.mkdir()
    (orphan / "generated_run.py").write_bytes(b"never execute")
    with TestClient(create_app(settings)) as restarted:
        recovered = restarted.get(f"{url}/{run['id']}").json()
        assert recovered["state"] == "FAILED"
        assert recovered["failure"]["code"] == "execution_interrupted"
        assert recovered["started_at"] is None
    assert not orphan.exists()
    assert list((settings.home / ".run-orphans").glob("*/generated_run.py"))


def test_package_readback_failure_creates_no_run(client, monkeypatch):
    from mlstudio.execution import service

    _, _, url, body, _ = ready(client)
    monkeypatch.setattr(
        service, "write_new", lambda *_: (_ for _ in ()).throw(OSError("disk full"))
    )
    assert client.post(url, json=body).status_code == 503
    assert client.get(url).json()["total"] == 0


def test_final_revision_check(client, monkeypatch):
    from mlstudio.execution import service
    from mlstudio.models import Project

    _, _, url, body, _ = ready(client)
    original = service.write_new

    def changed(path, data):
        original(path, data)
        if path.name == "package.json":
            with client.app.state.session_factory() as session:
                project = session.get(Project, url.split("/")[4])
                project.name = "Concurrent edit"
                session.commit()

    monkeypatch.setattr(service, "write_new", changed)
    assert client.post(url, json=body).status_code == 409
    assert client.get(url).json()["total"] == 0


def test_environment_and_pid_reuse(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("PYTHONPATH", "injection")
    monkeypatch.setenv("MLFLOW_TRACKING_TOKEN", "secret")
    env = process.environment()
    assert not {"AWS_SECRET_ACCESS_KEY", "PYTHONPATH", "MLFLOW_TRACKING_TOKEN"} & env.keys()
    assert env["OMP_NUM_THREADS"] == "1"
    assert process.owned_process({"pid": os.getpid(), "created": 0}, []) is None


def test_real_timeout_and_simultaneous_pipe_flood(client, monkeypatch, settings):
    settings.run_timeout_seconds = 0.4
    settings.run_log_bytes = 1024
    processes = []

    def launch(_args, directory):
        # Inject a real noisy workload only through the process adapter. Production
        # always launches the frozen script; no source artifact is rewritten here.
        child = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-u",
                "-c",
                "import os,time; [(os.write(1,b'a'*8192),os.write(2,b'b'*8192)) "
                "for _ in range(256)]; time.sleep(30)",
            ],
            cwd=directory,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=process.environment(),
        )
        processes.append(child)
        return child

    monkeypatch.setattr(process, "launch", launch)
    project, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    assert run["state"] == "FAILED" and run["failure"]["code"] == "timeout"
    assert processes[0].poll() is not None
    directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
    assert (directory / "stdout.log").stat().st_size == 1024
    assert (directory / "stderr.log").stat().st_size == 1024


@pytest.mark.parametrize(
    "mode,code",
    [
        ("missing", "model_missing"),
        ("empty", "model_invalid"),
        ("oversized", "model_invalid"),
        ("finalization", "artifact_finalization"),
    ],
)
def test_model_and_finalization_failures(client, monkeypatch, settings, mode, code):
    from mlstudio.execution import coordinator as module

    settings.run_model_bytes = 10

    def launch(_args, directory):
        plan = json.loads((directory / "execution_plan.json").read_bytes())
        result = {
            "schema_version": "mlstudio-result-v1",
            "status": "success",
            "dataset": plan["dataset"],
            "generator": plan["generator"],
            "versions": {
                "python": plan["implementation"]["python"],
                **plan["implementation"]["libraries"],
            },
            "metrics": {"accuracy": 1, "precision": 1, "recall": 1, "f1": 1, "roc_auc": 1},
            "roc_auc_unavailable_reason": None,
            "confusion_matrix": {
                "labels": [plan["target"]["negative_class"], plan["target"]["positive_class"]],
                "values": [[2, 0], [0, 2]],
            },
            "population": {"source": 20, "eligible": 20, "training": 16, "test": 4},
            "artifacts": {"model": {"kind": "complete_pipeline", "filename": "model.joblib"}},
        }
        (directory / ".pending/result.json").write_text(json.dumps(result))
        if mode != "missing":
            (directory / ".pending/model.joblib").write_bytes(
                b"" if mode == "empty" else b"x" * (11 if mode == "oversized" else 1)
            )
        if mode == "finalization":
            original = module.reference

            def fail(home, path, limit):
                if path.name == "model.joblib":
                    raise OSError("disk full")
                return original(home, path, limit)

            monkeypatch.setattr(module, "reference", fail)
        return Exited()

    fake_launch(monkeypatch, launch)
    _, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    assert run["state"] == "FAILED" and run["failure"]["code"] == code
    assert run["result"] is None and "model.joblib" not in run["artifacts"]


def test_freeze_includes_dormant_ir_and_terminal_immutability(client, monkeypatch, settings):
    from mlstudio.models import Run

    fake_launch(monkeypatch, lambda *_: Exited(1))
    project, _, url, body, _ = ready(client)
    configured = client.get(f"/api/v1/projects/{project['id']}/pipeline").json()["ir"]
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
    assert json.loads((directory / "pipeline_ir.json").read_bytes()) == configured
    assert configured["features"]["city"]["included"] is False
    with client.app.state.session_factory() as session:
        historical = session.get(Run, run["id"])
        historical.state = "SUCCEEDED"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()


def test_real_popen_contract(monkeypatch, tmp_path):
    observed = {}

    def popen(args, **kwargs):
        observed.update(args=args, **kwargs)
        return Exited()

    monkeypatch.setattr(process.subprocess, "Popen", popen)
    directory = tmp_path / "spaces café 数据"
    arguments = process.command(directory, tmp_path / "历史 source.csv")
    process.launch(arguments, directory)
    assert observed["shell"] is False and observed["stdin"] == subprocess.DEVNULL
    assert observed["cwd"] == directory and observed["args"] == arguments
    assert arguments[:6] == [os.path.abspath(sys.executable), "-I", "-B", "-u", "-X", "utf8"]
