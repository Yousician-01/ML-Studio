"""Frozen source availability is reported without repairing or rewriting history."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_projects_datasets import upload
from test_runs import ready, terminal

from mlstudio.execution.artifacts import digest
from mlstudio.execution.service import source_integrity


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("intact", "verified"),
        ("missing", "missing"),
        ("hash", "unavailable_or_corrupt"),
        ("size", "unavailable_or_corrupt"),
        ("unsafe", "unavailable_or_corrupt"),
        ("other_owner", "unavailable_or_corrupt"),
        ("identity", "unavailable_or_corrupt"),
        ("fingerprint", "unavailable_or_corrupt"),
        ("malformed", "unavailable_or_corrupt"),
        ("no_reference", "unavailable_or_corrupt"),
    ],
)
def test_frozen_source_reference(settings, damage, expected):
    project, dataset = str(uuid4()), str(uuid4())
    relative = f"projects/{project}/datasets/{dataset}/source.csv"
    path = settings.home / relative
    path.parent.mkdir(parents=True)
    content = b"feature,target\n1,yes\n2,no\n"
    path.write_bytes(content)
    run = SimpleNamespace(
        project_id=project,
        dataset_id=dataset,
        summary={"dataset_fingerprint": digest(content)},
        manifest={
            "project_id": project,
            "dataset_id": dataset,
            "dataset": {"path": relative, "size_bytes": len(content), "sha256": digest(content)},
        },
    )
    if damage == "missing":
        path.unlink()
    elif damage == "hash":
        path.write_bytes(content.replace(b"yes", b"YES"))  # Same size, different exact bytes.
    elif damage == "size":
        path.write_bytes(content + b"3,yes\n")
    elif damage == "unsafe":
        run.manifest["dataset"]["path"] = "../../outside.csv"
    elif damage == "other_owner":
        other = f"projects/{uuid4()}/datasets/{dataset}/source.csv"
        redirected = settings.home / other
        redirected.parent.mkdir(parents=True)
        redirected.write_bytes(content)  # Matching bytes never authorize another owner's path.
        run.manifest["dataset"]["path"] = other
    elif damage == "identity":
        run.manifest["dataset_id"] = str(uuid4())
    elif damage == "fingerprint":
        run.summary["dataset_fingerprint"] = "sha256:" + "0" * 64
    elif damage == "malformed":
        run.manifest["dataset"] = None
    elif damage == "no_reference":
        del run.manifest["dataset"]
    before = deepcopy(vars(run))
    status = source_integrity(run, settings.home)
    assert status["integrity"] == expected
    assert vars(run) == before
    assert "path" not in status
    if damage in {"malformed", "no_reference"}:
        assert status["size_bytes"] is None and status["sha256"] is None


def test_historical_api_retains_results_after_source_loss(client, settings):
    project, dataset, url, body, _ = ready(client)
    before = terminal(client, url, client.post(url, json=body).json()["id"])
    assert before["state"] == "SUCCEEDED"
    assert before["artifacts"]["dataset_source"]["integrity"] == "verified"
    # Availability must follow the frozen source, not the replacement active Dataset.
    assert upload(client, project, expected=dataset["id"]).status_code == 201
    path = settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    path.unlink()
    after = client.get(f"{url}/{before['id']}").json()
    assert after["artifacts"]["dataset_source"]["integrity"] == "missing"
    for field in ("state", "result", "summary", "started_at", "finished_at", "pipeline_ir"):
        assert after[field] == before[field]
    assert (
        client.get(url).json()["items"][0]["artifacts"]["dataset_source"]["integrity"] == "missing"
    )
