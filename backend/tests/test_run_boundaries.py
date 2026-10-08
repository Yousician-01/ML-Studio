"""Failure boundaries that cannot be established by the successful workload tests."""

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import joblib
import psutil
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from test_projects_datasets import configure, create, upload
from test_runs import Exited, fake_launch, ready, terminal
from test_train_configuration import save

from alembic import command
from mlstudio.core.config import Settings
from mlstudio.execution import process, service
from mlstudio.execution.artifacts import regular
from mlstudio.execution.results import ExecutionFailure
from mlstudio.execution.schemas import RunRequest
from mlstudio.main import create_app
from mlstudio.models import Run


@pytest.mark.parametrize("previous", ["base", "0003_working_pipeline"])
def test_migration_upgrade_and_parity(settings, previous):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    command.upgrade(config, previous)
    command.upgrade(config, "head")
    command.current(config, check_heads=True)
    command.check(config)


@pytest.mark.parametrize(
    "mutation",
    [
        {"state": "QUEUED"},
        {"sequence": 0},
        {"state": "RUNNING", "started_at": None},
        {"state": "SUCCEEDED", "finished_at": None},
        {"dataset_id": str(uuid4())},
    ],
)
def test_database_constraints(client, monkeypatch, mutation):
    fake_launch(monkeypatch, lambda *_: Exited(1))
    _, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    with client.app.state.session_factory() as session:
        row = session.get(Run, run["id"])
        values = {column.name: getattr(row, column.name) for column in Run.__table__.columns}
        values.update(id=str(uuid4()), request_id=str(uuid4()), sequence=2)
        values.update(mutation)
        with pytest.raises(IntegrityError):
            session.execute(insert(Run).values(**values))


def test_created_commit_failure_never_launches(client, monkeypatch, settings):
    project, _, url, body, _ = ready(client)
    original = Session.commit
    launches = []
    monkeypatch.setattr(process, "launch", lambda *_: launches.append(True))

    def fail(session):
        if any(isinstance(row, Run) for row in session.new):
            raise OperationalError("commit", {}, Exception("private"))
        return original(session)

    monkeypatch.setattr(Session, "commit", fail)
    assert client.post(url, json=body).status_code == 503
    assert client.get(url).json()["total"] == 0 and launches == []
    assert list((settings.home / "projects" / project["id"] / "runs").iterdir())
    monkeypatch.setattr(Session, "commit", original)
    fake_launch(monkeypatch, lambda *_: Exited(1))
    run = client.post(url, json=body).json()
    assert run["sequence"] == 1
    terminal(client, url, run["id"])
    assert list((settings.home / ".run-orphans").iterdir())


def test_worker_handoff_failure_is_terminal(client, monkeypatch):
    project, _, url, body, _ = ready(client)
    original = process.threading.Thread.start

    def start(thread):
        if thread.name == "mlstudio-execution":
            raise RuntimeError("no thread capacity")
        return original(thread)

    monkeypatch.setattr(process.threading.Thread, "start", start)
    response = client.post(url, json=body)
    assert response.status_code == 202
    run = terminal(client, url, response.json()["id"])
    assert run["failure"]["code"] == "launch_failure" and run["started_at"] is None


def test_running_commit_failure_preserves_launch_time(client, monkeypatch):
    fake_launch(monkeypatch, lambda *_: Exited(1))
    _, _, url, body, _ = ready(client)
    original = Session.commit

    def fail(session):
        if any(isinstance(row, Run) and row.state == "RUNNING" for row in session.dirty):
            raise OperationalError("commit", {}, Exception("private"))
        return original(session)

    monkeypatch.setattr(Session, "commit", fail)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    assert run["state"] == "FAILED" and run["started_at"] is not None


def test_terminal_commit_failure_cannot_expose_success(client, monkeypatch, settings):
    _, _, url, body, _ = ready(client)
    original = Session.commit

    def fail(session):
        if any(isinstance(row, Run) and row.state == "SUCCEEDED" for row in session.dirty):
            raise OperationalError("commit", {}, Exception("private"))
        return original(session)

    monkeypatch.setattr(Session, "commit", fail)
    response = client.post(url, json=body)
    worker = client.app.state.execution.worker
    worker.join(timeout=30)
    assert not worker.is_alive()
    run = client.get(f"{url}/{response.json()['id']}").json()
    assert run["state"] == "RUNNING" and run["result"] is None
    client.app.state.execution.close()
    monkeypatch.setattr(Session, "commit", original)
    with TestClient(create_app(settings)) as restarted:
        recovered = restarted.get(f"{url}/{run['id']}").json()
        assert recovered["state"] == "FAILED" and recovered["result"] is None
        assert "model.joblib" not in recovered["artifacts"]


def test_real_descendant_cleanup(tmp_path, settings):
    pid_file = tmp_path / "child-pid"
    script = (
        "import subprocess,sys,time,pathlib; "
        "p=subprocess.Popen([sys.executable,'-I','-c','import time; time.sleep(30)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(30)"
    )
    child = subprocess.Popen([sys.executable, "-I", "-c", script], shell=False)
    owner = psutil.Process(child.pid)
    descendant = None
    try:
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        descendant = psutil.Process(int(pid_file.read_text()))
        process.stop_tree(owner, settings.run_termination_grace_seconds)
        child.wait(timeout=5)
        assert not owner.is_running() and not descendant.is_running()
    finally:
        for proc in (descendant, owner):
            if proc is not None and proc.is_running():
                proc.kill()
        child.wait(timeout=5)


def test_uncertain_ownership_does_not_kill(monkeypatch):
    class Inaccessible:
        def create_time(self):
            return 10

        def cmdline(self):
            raise psutil.AccessDenied()

        def kill(self):
            pytest.fail("An unverified process must not be killed")

    monkeypatch.setattr(process.psutil, "Process", lambda *_: Inaccessible())
    with pytest.raises(ExecutionFailure, match="ownership_uncertain"):
        process.owned_process({"pid": 999, "created": 10}, ["expected"])


def test_recovery_missing_package_is_corruption(client, monkeypatch, settings):
    coordinator = client.app.state.execution
    monkeypatch.setattr(coordinator, "submit", lambda run_id, lease: coordinator.release(lease))
    project, _, url, body, _ = ready(client)
    run = client.post(url, json=body).json()
    source = settings.home / "projects" / project["id"] / "runs" / run["id"] / "generated_run.py"
    source.unlink()
    with TestClient(create_app(settings)) as restarted:
        recovered = restarted.get(f"{url}/{run['id']}").json()
        assert recovered["state"] == "FAILED" and recovered["failure"]["code"] == "package_corrupt"
        assert restarted.get(f"{url}/{run['id']}/code").status_code == 409
    assert not source.exists()


def test_model_links_rejected(tmp_path):
    original = tmp_path / "original"
    original.write_bytes(b"x")
    link = tmp_path / "model.joblib"
    try:
        link.symlink_to(original)
    except OSError:
        if sys.platform != "win32":
            raise
        # Windows file symlinks need a privilege; directory junctions do not.
        # Exercise an actual redirected model path on either platform.
        target = tmp_path / "redirected-model"
        target.mkdir()
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
        )
    with pytest.raises(ValueError):
        regular(link, 100)
    if link.is_junction():
        link.rmdir()


def test_real_mixed_pipeline_unicode_workspace(tmp_path):
    settings = Settings(home=tmp_path / "workspace café 数据", environment="test")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as client:
        project = create(client)
        rows = [
            f"{i if i % 7 else ''},{'west' if i % 2 else 'east'},{1 if i % 2 else 2}"
            for i in range(40)
        ]
        upload(client, project, ("age,city,label\n" + "\n".join(rows)).encode())
        configure(client, project, target_column="label")
        path = f"/api/v1/projects/{project['id']}/pipeline"
        state = client.get(path).json()
        state["ir"]["target"]["positive_class"] = {"value_type": "integer", "value": 1}
        state["ir"]["features"]["age"]["operations"] = [
            {"type": "impute", "strategy": "mean"},
            {"type": "scale", "method": "standard"},
        ]
        state["ir"]["features"]["city"]["operations"] = [{"type": "encode", "method": "one_hot"}]
        state["ir"].update(model={"type": "logistic_regression"}, split={})
        assert save(client, path, state).status_code == 200
        preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
        assert preview["ready"], preview
        body = {
            "request_id": str(uuid4()),
            "expected_revision": preview["revision"],
            "expected_source_sha256": preview["source_sha256"],
            "expected_plan_sha256": preview["plan_sha256"],
        }
        url = f"/api/v1/projects/{project['id']}/runs"
        run = terminal(client, url, client.post(url, json=body).json()["id"])
        assert run["state"] == "SUCCEEDED", run
        assert run["result"]["confusion_matrix"]["labels"][1] == {
            "value_type": "integer",
            "value": 1,
        }
        directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
        # Only trusted, test-produced models are loaded, never production ingestion.
        fitted = joblib.load(directory / "model.joblib")
        assert len(fitted.steps) == 2
        assert (directory / "generated_run.py").read_bytes() == preview["source"].encode()


def test_real_environment_mismatch(client, monkeypatch):
    from mlstudio.services import code_preview

    original = service.resolve

    def incompatible(*args):
        plan, issues = original(*args)
        if plan is not None:
            implementation = plan.implementation.model_copy(update={"python": "0.0.0"})
            plan = plan.model_copy(update={"implementation": implementation})
        return plan, issues

    monkeypatch.setattr(service, "resolve", incompatible)
    monkeypatch.setattr(code_preview, "resolve", incompatible)
    _, _, url, body, _ = ready(client)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    assert run["state"] == "FAILED"
    assert run["failure"]["stage"] == "runtime_inputs"
    assert run["result"] is None


def test_frozen_dataset_corruption_before_launch(client, monkeypatch, settings):
    project, dataset, url, body, _ = ready(client)
    coordinator = client.app.state.execution
    original = coordinator.submit

    def corrupt(run_id, lease):
        source = (
            settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
        )
        source.write_bytes(b"changed after freeze")
        original(run_id, lease)

    monkeypatch.setattr(coordinator, "submit", corrupt)
    run = terminal(client, url, client.post(url, json=body).json()["id"])
    assert run["failure"]["code"] == "dataset_mismatch"
    assert run["started_at"] is None


def test_package_readback_detects_corruption(client, monkeypatch):
    _, _, url, body, _ = ready(client)
    original = service.write_new

    def corrupt(path, data):
        original(path, data)
        if path.name == "generated_run.py":
            path.write_bytes(b"corrupt")

    monkeypatch.setattr(service, "write_new", corrupt)
    # Publication read-back detects this injected filesystem corruption before CREATED.
    assert client.post(url, json=body).status_code == 503
    assert client.get(url).json()["total"] == 0


def test_execution_outlives_request_session(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def launch(*_):
        entered.set()
        assert release.wait(10)
        return Exited(1)

    fake_launch(monkeypatch, launch)
    project, _, url, body, _ = ready(client)
    try:
        with client.app.state.session_factory() as request_session:
            run = service.create(
                request_session, project["id"], RunRequest(**body), client.app.state.execution
            )
            run_id = run.id
        # The request session and caller are gone before the workload returns.
        assert entered.wait(5)
    finally:
        release.set()
    assert terminal(client, url, run_id)["state"] == "FAILED"


def test_concurrent_duplicate_admission(client, monkeypatch):
    _, _, url, body, _ = ready(client)
    entered, release = threading.Event(), threading.Event()
    original = service.generate

    def blocked(plan):
        entered.set()
        assert release.wait(10)
        return original(plan)

    monkeypatch.setattr(service, "generate", blocked)
    fake_launch(monkeypatch, lambda *_: Exited(1))
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, url, json=body)
        try:
            assert entered.wait(5)
            # No committed request identity exists yet, so occupied capacity rejects
            # this overlapping submission rather than queuing a second attempt.
            assert client.post(url, json=body).status_code == 409
        finally:
            release.set()
        response = first.result(timeout=10)
    assert response.status_code == 202
    assert client.post(url, json=body).json()["id"] == response.json()["id"]
    terminal(client, url, response.json()["id"])
    assert client.get(url).json()["total"] == 1
