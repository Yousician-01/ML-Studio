"""Four focused managed-code execution scenarios; no visual training reruns."""

import hashlib
import time
from uuid import uuid4

import psutil
import pytest
from test_code_drafts import enter


def submit(client, source):
    project, _, draft, _, _ = enter(client)
    path = f"/api/v1/projects/{project['id']}/code-runs"
    body = {
        "draft_id": draft["id"],
        "revision": draft["revision"],
        "source": source,
        "request_id": str(uuid4()),
    }
    return project, draft, path, body


def finished(client, path, run_id):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = client.get(f"{path}/{run_id}")
        assert response.status_code == 200, response.text
        if response.json()["status"] not in ("PENDING", "RUNNING"):
            return response.json()
        time.sleep(0.05)
    pytest.fail("Code execution did not finish")


def test_success_records_exact_source_and_output(client, settings):
    project, draft, path, body = submit(client, "print('exact source executed', flush=True)\n")
    assert client.post(path, json=body).status_code == 403
    settings.code_execution_enabled = True
    assert (
        client.post(path, json=body, headers={"Origin": "https://untrusted.example"}).status_code
        == 403
    )
    started = client.post(path, json=body)
    assert started.status_code == 202, started.text
    run = finished(client, path, started.json()["id"])
    assert run["status"] == "COMPLETED" and run["exit_code"] == 0
    assert run["source"] == body["source"]
    assert run["source_sha256"] == "sha256:" + hashlib.sha256(body["source"].encode()).hexdigest()
    assert run["started_at"] and run["finished_at"] and run["duration_seconds"] >= 0
    assert run["source_integrity"] == "verified"
    assert (
        client.get(path + "/" + run["id"] + "/logs").json()["stdout"].strip()
        == "exact source executed"
    )
    assert client.post(path, json=body).json()["id"] == run["id"]
    assert (
        client.get(f"/api/v1/projects/{project['id']}/code-drafts/active").json()["source"]
        == body["source"]
    )
    assert client.get(f"/api/v1/projects/{project['id']}/runs").json()["total"] == 0
    other = client.post(
        "/api/v1/projects", json={"name": "Other", "problem_statement": "Other"}
    ).json()
    assert client.get(f"/api/v1/projects/{other['id']}/code-runs/{run['id']}").status_code == 404


def test_failed_execution_preserves_bounded_stderr_and_nonzero_exit(client, settings):
    settings.code_execution_enabled = True
    settings.run_log_bytes = 128
    _, _, path, body = submit(
        client,
        "import sys\nprint('failure evidence ' * 100, file=sys.stderr, flush=True)\n"
        "raise RuntimeError('expected')\n",
    )
    response = client.post(path, json=body)
    assert response.status_code == 202, response.text
    run = finished(client, path, response.json()["id"])
    assert run["status"] == "FAILED" and run["exit_code"] != 0
    logs = client.get(path + "/" + run["id"] + "/logs").json()
    assert "failure evidence" in logs["stderr"]
    assert len(logs["stderr"].encode()) <= 128 and logs["stderr_truncated"]
    assert run["configuration"]["timeout_seconds"] == settings.run_timeout_seconds


def test_cancel_stops_managed_tree_and_blocks_duplicate_execution(client, settings):
    settings.code_execution_enabled = True
    _, _, path, body = submit(
        client,
        "import subprocess,sys,time\n"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
        "print('CHILD='+str(p.pid),flush=True)\ntime.sleep(60)\n",
    )
    started = client.post(path, json=body)
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    deadline = time.monotonic() + 10
    child_pid = None
    while time.monotonic() < deadline:
        output = client.get(f"{path}/{run_id}/logs").json()["stdout"]
        if "CHILD=" in output:
            child_pid = int(output.split("CHILD=")[1].splitlines()[0])
            break
        time.sleep(0.05)
    detail = client.get(f"{path}/{run_id}").json()
    assert child_pid is not None, (detail["status"], detail["error"])
    assert client.post(path, json={**body, "request_id": str(uuid4())}).status_code == 409
    assert client.post(f"{path}/{run_id}/cancel").status_code == 200
    assert finished(client, path, run_id)["status"] == "CANCELLED"
    assert (
        not psutil.pid_exists(child_pid)
        or psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE
    )


def test_historical_source_is_independent_of_future_draft_edits(client, settings):
    from mlstudio.models import CodeRun

    settings.code_execution_enabled = True
    project, draft, path, body = submit(client, "print('original')\n")
    started = client.post(path, json=body)
    assert started.status_code == 202, started.text
    before = finished(client, path, started.json()["id"])
    draft_path = f"/api/v1/projects/{project['id']}/code-drafts"
    current = client.get(draft_path + "/active").json()
    assert (
        client.patch(
            draft_path + "/" + draft["id"],
            json={"revision": current["revision"], "source": "print('future')"},
        ).status_code
        == 200
    )
    assert client.get(path + "/" + before["id"]).json() == before
    assert client.get(path).json()["items"][0]["id"] == before["id"]
    with client.app.state.session_factory() as session:
        row = session.get(CodeRun, before["id"])
        row.source = "changed"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
