import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from alembic import command
from mlstudio.main import create_app
from mlstudio.models import Dataset, Project
from mlstudio.services.artifacts import source_path

CSV = (
    b"customer_id,amount,segment,churn,alternate\r\n1,1.5,east,yes,0\r\n"
    b"2,2.7,west,no,1\r\n3,,north,,0\r\n4,4.1,east,yes,1\r\n"
)


def create(client):
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Churn",
            "description": "Subscriptions",
            "problem_statement": "Predict churn.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, project, content=CSV, filename="customers.csv", expected=None):
    return client.post(
        f"/api/v1/projects/{project['id']}/dataset",
        files={"file": (filename, content, "text/csv")},
        data={"expected_dataset_id": expected} if expected else {},
    )


def configure(client, project, **changes):
    current = client.get(f"/api/v1/projects/{project['id']}/dataset").json()
    return client.patch(
        f"/api/v1/projects/{project['id']}/dataset",
        json={
            "dataset_id": current["id"],
            "revision": current["revision"],
            **changes,
        },
    )


def test_project_crud_and_restart(client, settings):
    assert client.get("/api/v1/projects").json() == []
    project = create(client)
    path = f"/api/v1/projects/{project['id']}"
    assert project["ml_objective"] == "binary_classification"
    assert project["active_dataset_id"] is None
    assert project["target_column"] is None
    assert project["created_at"].endswith("Z")
    assert client.get(path).json() == project
    assert client.get("/api/v1/projects").json() == [project]
    updated = client.patch(
        path,
        json={"name": "Retention", "description": None, "success_context": "Find likely churners."},
    ).json()
    assert updated["name"] == "Retention"
    assert updated["created_at"] == project["created_at"]
    assert updated["updated_at"] > project["updated_at"]
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path).json() == updated
    assert client.get("/api/v1/projects/unknown").status_code == 404
    assert client.patch("/api/v1/projects/unknown", json={"name": "x"}).status_code == 404
    assert client.get(path + "/dataset").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "problem_statement": "x"},
        {"name": "x", "problem_statement": " "},
        {"name": "x"},
        {"name": "x", "problem_statement": "x", "ml_objective": "regression"},
    ],
)
def test_project_input_validation(client, body):
    assert client.post("/api/v1/projects", json=body).status_code == 422


def test_required_project_fields_cannot_be_cleared(client):
    project = create(client)
    for field in ("name", "problem_statement"):
        assert (
            client.patch(f"/api/v1/projects/{project['id']}", json={field: None}).status_code == 422
        )


def test_ingestion_preserves_bytes_and_metadata(client, settings):
    project = create(client)
    response = upload(client, project)
    assert response.status_code == 201, response.text
    data = response.json()
    path = source_path(settings.home, project["id"], data["id"])
    assert path.read_bytes() == CSV
    assert data["fingerprint"] == "sha256:" + hashlib.sha256(CSV).hexdigest()
    assert data["row_count"] == 4 and data["column_count"] == 5
    assert data["missing_cells"] == 2 and data["duplicate_rows"] == 0
    assert data["preview"][2] == [3, None, "north", None, 0]
    assert all(column["role"] == "feature" for column in data["columns"])
    with client.app.state.session_factory() as session:
        stored = session.get(Dataset, data["id"])
        assert stored.original_filename == "customers.csv"
        assert (
            stored.source_relative_path
            == f"projects/{project['id']}/datasets/{data['id']}/source.csv"
        )
        assert stored.fingerprint == data["fingerprint"]
        assert stored.parsing_version == "csv-utf8-v1"
        assert session.get(Project, project["id"]).active_dataset_id == data["id"]
        assert "preview" not in inspect(Dataset).columns
        assert "yes" not in str(stored.columns)  # Observed class values are not persisted.
    assert not list((settings.home / ".ingestion").iterdir())


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"a,b\n",
        b"\n\n",
        b"a,b\n1,2,3\n",
        b"a,b\n1\n",
        b'a,b\n"unterminated,2\n',
        b"a,a\n1,2\n",
        b",b\n1,2\n",
        b"\xff\xfe\x00\x10",
        b"a,b\n1,\x00\n",
        b"a\ninf\n",
        b"not a csv",
    ],
)
def test_invalid_upload_keeps_current_source(client, settings, content):
    project = create(client)
    original = upload(client, project).json()
    response = upload(client, project, content, expected=original["id"])
    assert response.status_code == 422, response.text
    assert str(settings.home) not in response.text
    current = client.get(f"/api/v1/projects/{project['id']}").json()
    assert current["active_dataset_id"] == original["id"]
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(Dataset)).all()) == 1
    assert not list((settings.home / ".ingestion").iterdir())


def test_size_limit_and_path_traversal(client, settings):
    project = create(client)
    data = upload(client, project, filename="../../outside.csv").json()
    assert source_path(settings.home, project["id"], data["id"]).read_bytes() == CSV
    assert not (settings.home.parent / "outside.csv").exists()
    settings.max_csv_upload_bytes = 8
    response = upload(client, project, expected=data["id"])
    assert response.status_code == 413
    assert "8 byte" in response.json()["detail"]


def test_multipart_request_limit_before_spooling(client, settings):
    # A second app uses a small limit; multipart overhead allowance is 1 MiB.
    settings.max_csv_upload_bytes = 8
    with TestClient(create_app(settings)) as bounded:
        project = create(bounded)
        response = upload(bounded, project, b"x" * (1024 * 1024 + 100))
        assert response.status_code == 413, response.text


def test_overrides_targets_and_restart(client, settings):
    project = create(client)
    upload(client, project)
    changed = configure(client, project, semantic_overrides={"amount": "categorical"}).json()
    column = changed["columns"][1]
    assert column["inferred_semantic_type"] == "continuous"
    assert column["semantic_override"] == column["effective_semantic_type"] == "categorical"
    selected = configure(client, project, target_column="churn")
    assert selected.status_code == 200, selected.text
    assert selected.json()["target_classes"] == ["yes", "no"]
    assert selected.json()["columns"][3]["role"] == "target"
    changed_target = configure(client, project, target_column="alternate").json()
    assert changed_target["target_classes"] == [0, 1]
    assert type(changed_target["target_classes"][0]) is int
    assert changed_target["columns"][3]["role"] == "excluded"
    assert [column["role"] for column in changed_target["columns"]].count("target") == 1
    with TestClient(create_app(settings)) as restarted:
        saved = restarted.get(f"/api/v1/projects/{project['id']}/dataset").json()
        assert saved == changed_target
    reset = configure(client, project, semantic_overrides={"amount": None}).json()["columns"][1]
    assert reset["semantic_override"] is None
    assert reset["effective_semantic_type"] == reset["inferred_semantic_type"] == "continuous"
    cleared = configure(client, project, target_column=None).json()
    assert all(column["role"] != "target" for column in cleared["columns"])


@pytest.mark.parametrize(
    "values,classes",
    [
        ("yes\nno\nyes", ["yes", "no"]),
        ("1\n2\n1", [1, 2]),
        ("True\nFalse\nTrue", [True, False]),
        ("1.5\n2.5\n1.5", [1.5, 2.5]),
        ('A\nB\n""', ["A", "B"]),
    ],
)
def test_typed_binary_classes(client, values, classes):
    project = create(client)
    assert upload(client, project, ("label\n" + values + "\n").encode()).status_code == 201
    response = configure(client, project, target_column="label")
    assert response.status_code == 200, response.text
    observed = response.json()["target_classes"]
    assert observed == classes
    assert [type(value) for value in observed] == [type(value) for value in classes]


@pytest.mark.parametrize("values,count", [("A\nA\nA", 1), ("A\nB\nC", 3), ('""\n""', 0)])
def test_invalid_target_does_not_drop_classes(client, values, count):
    project = create(client)
    upload(client, project, ("label\n" + values + "\n").encode())
    response = configure(
        client, project, target_column="label", semantic_overrides={"label": "binary"}
    )
    assert response.status_code == 422
    assert f"has {count}" in response.json()["detail"]
    data = client.get(f"/api/v1/projects/{project['id']}/dataset").json()
    assert data["target_column"] is None
    assert data["columns"][0]["semantic_override"] is None


def test_replacement_retains_old_artifact_and_resets_configuration(client, settings):
    project = create(client)
    first = upload(client, project).json()
    configure(client, project, target_column="churn", semantic_overrides={"amount": "text"})
    assert upload(client, project).status_code == 409  # No accidental second upload.
    second = upload(client, project, CSV + b"5,5.5,west,no,0\r\n", expected=first["id"]).json()
    assert first["id"] != second["id"]
    assert first["fingerprint"] != second["fingerprint"]
    assert second["target_column"] is None
    assert all(column["semantic_override"] is None for column in second["columns"])
    assert source_path(settings.home, project["id"], first["id"]).read_bytes() == CSV
    with client.app.state.session_factory() as session:
        assert session.get(Dataset, first["id"]) is not None
        assert session.get(Project, project["id"]).active_dataset_id == second["id"]
    assert upload(client, project, expected=first["id"]).status_code == 409


def test_stale_configuration_and_unknown_columns_rejected(client):
    project = create(client)
    source = upload(client, project).json()
    path = f"/api/v1/projects/{project['id']}/dataset"
    assert (
        client.patch(
            path, json={"dataset_id": source["id"], "revision": 1, "target_column": "churn"}
        ).status_code
        == 409
    )
    assert configure(client, project, target_column="missing").status_code == 422
    assert configure(client, project, semantic_overrides={"missing": "binary"}).status_code == 422
    assert configure(client, project, semantic_overrides={"amount": "made-up"}).status_code == 422


def test_preview_limit_and_duplicate_count(client):
    project = create(client)
    source = upload(client, project, b"x,y\n" + b"1,a\n" * 30).json()
    assert source["row_count"] == 30 and source["duplicate_rows"] == 29
    assert len(source["preview"]) == source["preview_limit"] == 20


def test_integrity_failure_preserves_metadata(client, settings):
    project = create(client)
    source = upload(client, project).json()
    path = source_path(settings.home, project["id"], source["id"])
    path.write_bytes(b"changed")
    endpoint = f"/api/v1/projects/{project['id']}/dataset"
    assert client.get(endpoint).status_code == 409
    path.unlink()
    assert client.get(endpoint).status_code == 409
    assert (
        client.get(f"/api/v1/projects/{project['id']}").json()["active_dataset_id"] == source["id"]
    )


def test_cross_project_active_reference_constraint(client):
    first, second = create(client), create(client)
    source = upload(client, first).json()
    with client.app.state.session_factory() as session:
        session.get(Project, second["id"]).active_dataset_id = source["id"]
        with pytest.raises(IntegrityError):
            session.commit()


def test_failed_commit_cleans_artifact_and_preserves_active(client, settings, monkeypatch):
    project = create(client)
    first = upload(client, project).json()
    from sqlalchemy.orm import Session

    def fail(_session):
        raise StaleDataError("simulated concurrent change")

    monkeypatch.setattr(Session, "commit", fail)
    response = upload(client, project, expected=first["id"])
    assert response.status_code == 409
    directory = settings.home / "projects" / project["id"] / "datasets"
    assert [path.name for path in directory.iterdir()] == [first["id"]]
    assert (
        client.get(f"/api/v1/projects/{project['id']}").json()["active_dataset_id"] == first["id"]
    )


def test_phase0_upgrade(settings):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    command.upgrade(config, "0001_foundation")
    command.upgrade(config, "head")
    with TestClient(create_app(settings)) as client:
        create(client)


def test_bom_quoted_fields_and_duplicate_rows(client, settings):
    project = create(client)
    content = (
        b'\xef\xbb\xbftext,label\r\n"hello, world",yes\r\n"hello, world",yes\r\n"two\nlines",no\r\n'
    )
    result = upload(client, project, content)
    assert result.status_code == 201, result.text
    source = result.json()
    assert source["row_count"] == 3 and source["duplicate_rows"] == 1
    assert source["preview"][-1] == ["two\nlines", "no"]
    assert source_path(settings.home, project["id"], source["id"]).read_bytes() == content


def test_dataset_owner_foreign_key_and_concurrent_project_update(client):
    project = create(client)
    source = upload(client, project).json()
    with client.app.state.session_factory() as first, client.app.state.session_factory() as second:
        first_project = first.get(Project, project["id"])
        second_project = second.get(Project, project["id"])
        first_project.name = "First update"
        first.commit()
        second_project.name = "Stale update"
        with pytest.raises(StaleDataError):
            second.commit()
    with client.app.state.session_factory() as session:
        session.get(Dataset, source["id"]).project_id = "missing-project"
        with pytest.raises(IntegrityError):
            session.commit()


def test_generated_id_collision_cannot_delete_existing_source(client, settings, monkeypatch):
    project = create(client)
    source = upload(client, project).json()
    monkeypatch.setattr("mlstudio.services.datasets.new_id", lambda: source["id"])
    result = upload(client, project, expected=source["id"])
    assert result.status_code == 503
    assert source_path(settings.home, project["id"], source["id"]).read_bytes() == CSV


@pytest.mark.parametrize(
    "values",
    [
        [9007199254740992, 9007199254740993],
        [-9007199254740992, -9007199254740993],
        [9007199254740991, 9007199254740992],
        [-9007199254740991, -9007199254740992],
    ],
)
def test_lossless_integer_csv_api_and_frontend(client, values):
    project = create(client)
    content = ("label\n" + "\n".join(map(str, values)) + "\n").encode()
    assert upload(client, project, content).status_code == 201
    response = configure(client, project, target_column="label")
    assert response.status_code == 200, response.text
    expected = [
        {"value_type": "integer", "value": str(value)} if abs(value) > 2**53 - 1 else value
        for value in values
    ]
    assert response.json()["target_classes"] == expected
    assert response.json()["preview"] == [[value] for value in expected]
    # Exercise JSON.parse and the exact rendering helper used by both UI tables/classes.
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to verify the browser boundary")
    helper = Path(__file__).resolve().parents[2] / "frontend/src/lib/api/scalars.ts"
    script = """
        import assert from 'node:assert/strict';
        import { readFileSync } from 'node:fs';
        const { displayScalar } = await import(process.argv[1]);
        const snapshot = JSON.parse(readFileSync(0, 'utf8'));
        const labels = snapshot.target_classes.map(value => displayScalar(value, true));
        const rows = snapshot.preview.map(row => displayScalar(row[0]));
        assert.equal(new Set(labels).size, 2);
        assert.deepEqual(labels, process.argv.slice(2));
        assert.deepEqual(rows, labels);
    """
    result = subprocess.run(
        [
            node,
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script,
            helper.as_uri(),
            *map(str, values),
        ],
        input=response.text,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_displayed_snapshot_revision_conflict_and_metadata_update(client):
    project = create(client)
    path = f"/api/v1/projects/{project['id']}"
    initial = upload(client, project).json()
    assert initial["revision"] == client.get(path).json()["revision"]
    displayed_a = client.get(path + "/dataset").json()
    updated_b = client.patch(
        path + "/dataset",
        json={
            "dataset_id": displayed_a["id"],
            "revision": displayed_a["revision"],
            "semantic_overrides": {"amount": "text"},
        },
    ).json()
    assert updated_b["revision"] == displayed_a["revision"] + 1
    # A separately fetched newer Project must not become the displayed snapshot's token.
    assert client.get(path).json()["revision"] == updated_b["revision"]
    stale = client.patch(
        path + "/dataset",
        json={
            "dataset_id": displayed_a["id"],
            "revision": displayed_a["revision"],
            "semantic_overrides": {"amount": "categorical"},
        },
    )
    assert stale.status_code == 409
    assert client.get(path + "/dataset").json() == updated_b
    metadata = client.patch(path, json={"name": "Updated context"}).json()
    assert metadata["revision"] == updated_b["revision"] + 1
    assert (
        client.patch(
            path + "/dataset",
            json={
                "dataset_id": updated_b["id"],
                "revision": updated_b["revision"],
                "target_column": "churn",
            },
        ).status_code
        == 409
    )
    refreshed = client.get(path + "/dataset").json()
    assert refreshed["revision"] == metadata["revision"]
    assert refreshed["columns"][1]["semantic_override"] == "text"
    saved = client.patch(
        path + "/dataset",
        json={
            "dataset_id": refreshed["id"],
            "revision": refreshed["revision"],
            "target_column": "churn",
        },
    ).json()
    assert saved["revision"] == refreshed["revision"] + 1
    assert client.get(path + "/dataset").json() == saved


def test_dataset_read_refreshes_configuration_and_revision_together(client, settings):
    from mlstudio.services.datasets import read_dataset

    project = create(client)
    upload(client, project)
    with client.app.state.session_factory() as stale_session:
        stale_project = stale_session.get(Project, project["id"])
        old_revision = stale_project.revision
        updated = configure(client, project, semantic_overrides={"amount": "text"}).json()
        assert stale_project.revision == old_revision
        snapshot = read_dataset(stale_session, stale_project, settings).model_dump()
        assert snapshot == updated
