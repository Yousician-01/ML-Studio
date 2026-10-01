from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from mlstudio.models import Dataset


def project_with_sources(client):
    project = client.post(
        "/api/v1/projects", json={"name": "Disposable", "problem_statement": "Test deletion."}
    ).json()
    path = f"/api/v1/projects/{project['id']}"
    first = client.post(path + "/dataset", files={"file": ("one.csv", b"label\na\nb\n")}).json()
    client.post(
        path + "/dataset",
        files={"file": ("two.csv", b"label\nx\ny\n")},
        data={"expected_dataset_id": first["id"]},
    )
    return client.get(path).json()


def remove(client, project):
    return client.delete(
        f"/api/v1/projects/{project['id']}", params={"revision": project["revision"]}
    )


def test_delete_retained_sources_metadata_and_isolation(client, settings):
    first, second = project_with_sources(client), project_with_sources(client)
    owned = settings.home / "projects" / first["id"]
    assert len(list(owned.glob("datasets/*/source.csv"))) == 2
    assert remove(client, first).status_code == 204
    assert not owned.exists()
    assert not (settings.home / ".deleting" / first["id"]).exists()
    assert client.get(f"/api/v1/projects/{first['id']}").status_code == 404
    assert [p["id"] for p in client.get("/api/v1/projects").json()] == [second["id"]]
    assert len(list((settings.home / "projects" / second["id"]).glob("datasets/*/source.csv"))) == 2
    with client.app.state.session_factory() as session:
        assert session.scalars(select(Dataset).where(Dataset.project_id == first["id"])).all() == []
    assert remove(client, first).status_code == 404


def test_empty_project_unknown_and_stale_delete(client):
    project = client.post(
        "/api/v1/projects", json={"name": "Empty", "problem_statement": "Empty."}
    ).json()
    path = f"/api/v1/projects/{project['id']}"
    fresh = client.patch(path, json={"name": "Renamed"}).json()
    assert remove(client, project).status_code == 409
    assert remove(client, fresh).status_code == 204
    assert client.delete("/api/v1/projects/unknown", params={"revision": 1}).status_code == 404


def test_delete_db_failure_restores_artifacts(client, settings):
    project = project_with_sources(client)
    with patch.object(Session, "commit", side_effect=OperationalError("internal", {}, Exception())):
        assert remove(client, project).status_code == 503
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200
    assert (
        len(list((settings.home / "projects" / project["id"]).glob("datasets/*/source.csv"))) == 2
    )
    assert not (settings.home / ".deleting" / project["id"]).exists()


def test_delete_rename_failure_keeps_metadata(client):
    project = project_with_sources(client)
    with patch.object(Path, "rename", side_effect=PermissionError("private path")):
        response = remove(client, project)
        assert response.status_code == 503 and "private path" not in response.text
    assert client.get(f"/api/v1/projects/{project['id']}/dataset").status_code == 200


def test_cleanup_failure_is_retryable(client, settings):
    project = project_with_sources(client)
    with patch("mlstudio.services.project_deletion.shutil.rmtree", side_effect=PermissionError()):
        response = remove(client, project)
        assert response.status_code == 503 and "Retry deletion" in response.text
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert (settings.home / ".deleting" / project["id"]).exists()
    assert remove(client, project).status_code == 204
    assert not (settings.home / ".deleting" / project["id"]).exists()


def test_retry_recovers_precommit_rename(client, settings):
    project = project_with_sources(client)
    stage = settings.home / ".deleting" / project["id"]
    stage.parent.mkdir()
    (settings.home / "projects" / project["id"]).rename(stage)
    assert remove(client, project).status_code == 204
    assert not stage.exists()


def test_delete_rejects_linked_directory(client, settings, monkeypatch):
    project = project_with_sources(client)
    owned = settings.home / "projects" / project["id"]
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == owned or original(path))
    assert remove(client, project).status_code == 409
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200


def test_overlapping_delete_cannot_recover_a_live_transaction(client, settings, monkeypatch):
    project = project_with_sources(client)
    original = settings.home / "projects" / project["id"]
    staged = settings.home / ".deleting" / project["id"]
    ready, second_flush = Event(), Event()
    commit, flush = Session.commit, Session.flush
    observations = []

    def paused_commit(session):
        ready.set()  # First request has staged its directory but has not committed.
        assert second_flush.wait(5)
        return commit(session)

    def observed_flush(session, *args, **kwargs):
        if ready.is_set() and session.dirty and not second_flush.is_set():
            observations.append(staged.exists() and not original.exists())
            second_flush.set()
        return flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "commit", paused_commit)
    monkeypatch.setattr(Session, "flush", observed_flush)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(remove, client, project)
        assert ready.wait(5)
        second = pool.submit(remove, client, project)
        assert first.result(timeout=10).status_code == 204
        assert second.result(timeout=10).status_code == 409
    assert observations == [True]
    assert not original.exists() and not staged.exists()
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
