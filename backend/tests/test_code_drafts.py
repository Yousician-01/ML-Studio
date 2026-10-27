"""Editable source is independent of visual intent and immutable execution history."""

import hashlib
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_regression_runs import ready_regression

from mlstudio.main import create_app


def enter(client):
    project, _, _, _, preview = ready_regression(client)
    path = f"/api/v1/projects/{project['id']}/code-drafts"
    body = {
        "revision": preview["revision"],
        "source_sha256": preview["source_sha256"],
        "plan_sha256": preview["plan_sha256"],
    }
    original = client.get(f"/api/v1/projects/{project['id']}/pipeline").json()["ir"]
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return project, path, response.json(), preview, original


def test_enter_reopen_save_and_original_configuration(client, settings):
    project, path, draft, preview, original = enter(client)
    assert draft["baseline_source"] == draft["source"] == preview["source"]
    assert draft["origin_ir"] == original
    assert draft["origin_revision"] == preview["revision"]
    assert not draft["modified"] and draft["status"] == "active"
    assert client.get(path + "/active").json()["id"] == draft["id"]
    source = draft["source"] + "\n# manual change\n"
    saved = client.patch(
        path + "/" + draft["id"], json={"revision": draft["revision"], "source": source}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["modified"]
    assert saved.json()["baseline_source"] == preview["source"]
    with TestClient(create_app(settings)) as restarted:
        reopened = restarted.get(path + "/active").json()
        assert reopened["source"] == source
        assert reopened["origin_ir"] == original
        assert restarted.get(f"/api/v1/projects/{project['id']}/pipeline").json()["ir"] == original
        assert restarted.get(f"/api/v1/projects/{project['id']}/runs").json()["total"] == 0


def test_revision_conflicts_and_cross_project_access(client):
    _, path, draft, _, _ = enter(client)
    body = {"revision": draft["revision"], "source": "# changed"}
    assert client.patch(path + "/" + draft["id"], json=body).status_code == 200
    assert client.patch(path + "/" + draft["id"], json=body).status_code == 409
    other = client.post(
        "/api/v1/projects", json={"name": "Other", "problem_statement": "Other"}
    ).json()
    assert (
        client.get(f"/api/v1/projects/{other['id']}/code-drafts/{draft['id']}").status_code == 404
    )


@pytest.mark.parametrize("action", ["discard", "save_snapshot"])
def test_visual_reentry_requires_explicit_action(client, action):
    project, path, draft, _, original = enter(client)
    base = f"/api/v1/projects/{project['id']}"
    state = client.get(base + "/pipeline").json()
    assert (
        client.patch(
            base + "/pipeline", json={"revision": state["revision"], "ir": original}
        ).status_code
        == 409
    )
    dataset = client.get(base + "/dataset").json()
    assert (
        client.patch(
            base + "/dataset",
            json={
                "dataset_id": dataset["id"],
                "revision": dataset["revision"],
                "target_column": None,
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + "/dataset",
            files={"file": ("new.csv", b"x,y\n1,2\n")},
            data={"expected_dataset_id": dataset["id"]},
        ).status_code
        == 409
    )
    source = draft["source"] + "\n# unsaved manual source"
    exited = client.post(
        path + "/" + draft["id"] + "/exit",
        json={"revision": draft["revision"], "action": action, "source": source},
    )
    assert exited.status_code == 200, exited.text
    assert exited.json()["status"] == ("discarded" if action == "discard" else "archived")
    assert client.get(path + "/active").json() is None
    current = client.get(base + "/pipeline").json()
    assert current["ir"] == original
    snapshots = client.get(path + "/" + draft["id"] + "/snapshots").json()
    assert len(snapshots) == (0 if action == "discard" else 1)
    if snapshots:
        frozen = client.get(path + "/" + draft["id"] + "/snapshots/" + snapshots[0]["id"]).json()
        assert frozen["source"] == source
        assert frozen["source_sha256"] == "sha256:" + hashlib.sha256(source.encode()).hexdigest()
    assert (
        client.patch(
            base + "/pipeline", json={"revision": current["revision"], "ir": original}
        ).status_code
        == 200
    )


def test_snapshot_is_not_execution_and_cannot_be_overwritten(client):
    _, path, draft, _, _ = enter(client)
    payload = {
        "revision": draft["revision"],
        "source": "# arbitrary Python, not executed\nraise RuntimeError()\n",
    }
    saved = client.post(path + "/" + draft["id"] + "/snapshots", json=payload)
    assert saved.status_code == 201, saved.text
    snapshot = saved.json()["snapshot"]
    assert snapshot["source"] == payload["source"]
    current = client.get(path + "/active").json()
    client.patch(
        path + "/" + draft["id"], json={"revision": current["revision"], "source": "# newer"}
    )
    assert client.get(path + "/" + draft["id"] + "/snapshots/" + snapshot["id"]).json() == snapshot
    assert (
        client.patch(
            path + "/" + draft["id"] + "/snapshots/" + snapshot["id"], json=payload
        ).status_code
        == 405
    )


def test_unreviewed_entry_and_duplicate_session_rejected(client):
    project, _, _, _, preview = ready_regression(client)
    path = f"/api/v1/projects/{project['id']}/code-drafts"
    body = {
        "revision": preview["revision"],
        "source_sha256": "sha256:" + "0" * 64,
        "plan_sha256": preview["plan_sha256"],
    }
    assert client.post(path, json=body).status_code == 409
    body["source_sha256"] = preview["source_sha256"]
    assert client.post(path, json=body).status_code == 201
    body["revision"] = client.get(f"/api/v1/projects/{project['id']}").json()["revision"]
    assert client.post(path, json=body).status_code == 409


def test_source_validation_and_closed_draft_cannot_be_saved(client):
    _, path, draft, _, _ = enter(client)
    for source in ("\x00bad", "a" * 1048577):
        assert (
            client.patch(
                path + "/" + draft["id"], json={"revision": draft["revision"], "source": source}
            ).status_code
            == 422
        )
    assert (
        client.post(
            path + "/" + draft["id"] + "/exit",
            json={"revision": draft["revision"], "action": "discard"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path + "/" + draft["id"], json={"revision": draft["revision"], "source": ""}
        ).status_code
        == 409
    )


def test_historical_rows_and_artifacts_are_untouched(client, settings):
    from sqlalchemy import select
    from test_runs import ready, terminal
    from test_tracking import joined

    from mlstudio.models import Run

    project, _, url, body, _ = ready(client)
    response = client.post(url, json=body)
    run = terminal(client, url, response.json()["id"])
    joined(client)
    before = client.get(url + "/" + run["id"]).json()
    code = client.get(url + "/" + run["id"] + "/code").json()
    directory = settings.home / "projects" / project["id"] / "runs" / run["id"]
    artifacts = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
    path = f"/api/v1/projects/{project['id']}/code-drafts"
    draft = client.post(
        path,
        json={
            "revision": preview["revision"],
            "source_sha256": preview["source_sha256"],
            "plan_sha256": preview["plan_sha256"],
        },
    ).json()
    assert client.post(url, json=body).json()["id"] == run["id"]
    assert client.post(url, json={**body, "request_id": str(uuid4())}).status_code == 409
    assert (
        client.post(
            path + "/" + draft["id"] + "/exit",
            json={
                "revision": draft["revision"],
                "action": "save_snapshot",
                "source": "print('not run')",
            },
        ).status_code
        == 200
    )
    assert client.get(url + "/" + run["id"]).json() == before
    assert client.get(url + "/" + run["id"] + "/code").json() == code
    assert artifacts == {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    with client.app.state.session_factory() as session:
        row = session.scalar(select(Run).where(Run.id == run["id"]))
        assert deepcopy(row.result) == before["result"]


def test_origin_and_snapshot_are_immutable_and_active_session_is_unique(client):
    from sqlalchemy.exc import IntegrityError

    from mlstudio.models import CodeDraft, CodeSnapshot

    _, path, draft, _, _ = enter(client)
    frozen = client.post(
        path + "/" + draft["id"] + "/snapshots",
        json={"revision": draft["revision"], "source": "# frozen"},
    ).json()["snapshot"]
    with client.app.state.session_factory() as session:
        row = session.get(CodeDraft, draft["id"])
        row.origin_ir = {"attempt": "rewrite visual history"}
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()
        snapshot = session.get(CodeSnapshot, frozen["id"])
        snapshot.source = "# changed"
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
        session.rollback()
        duplicate = {key: value for key, value in draft.items() if key != "modified"}
        session.add(CodeDraft(**{**duplicate, "id": str(uuid4())}))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_project_deletion_cascades_owned_drafts_and_snapshots(client):
    from mlstudio.models import CodeDraft, CodeSnapshot

    project, path, draft, _, _ = enter(client)
    frozen = client.post(
        path + "/" + draft["id"] + "/snapshots",
        json={
            "revision": draft["revision"],
            "source": "# retained until explicit Project deletion",
        },
    ).json()["snapshot"]
    current = client.get(f"/api/v1/projects/{project['id']}").json()
    assert (
        client.delete(
            f"/api/v1/projects/{project['id']}?revision={current['revision']}"
        ).status_code
        == 204
    )
    with client.app.state.session_factory() as session:
        assert session.get(CodeDraft, draft["id"]) is None
        assert session.get(CodeSnapshot, frozen["id"]) is None
