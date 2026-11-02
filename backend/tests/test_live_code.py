from copy import deepcopy

from test_code_drafts import enter
from test_regression_runs import ready_regression


def test_unsaved_preview_and_draft_do_not_save_visual_intent(client):
    project, _, _, _, original = ready_regression(client)
    base = f"/api/v1/projects/{project['id']}"
    state = client.get(base + "/pipeline").json()
    ir = deepcopy(state["ir"])
    ir["model"]["parameters"]["fit_intercept"] = False
    ir["features"][next(iter(ir["features"]))]["operations"] = []
    response = client.post(base + "/code/preview", json={"revision": state["revision"], "ir": ir})
    assert response.status_code == 200, response.text
    generated = response.json()
    assert generated["ready"]
    assert generated["source_sha256"] != original["source_sha256"]
    assert client.get(base + "/pipeline").json() == state
    assert client.get(base + "/code-drafts").json() == []
    assert client.get(base + "/runs").json()["total"] == 0
    invalid = deepcopy(ir)
    invalid["model"] = None
    assert not client.post(
        base + "/code/preview", json={"revision": state["revision"], "ir": invalid}
    ).json()["ready"]
    assert (
        client.post(
            base + "/code/preview", json={"revision": state["revision"] + 1, "ir": ir}
        ).status_code
        == 409
    )
    draft = client.post(
        base + "/code-drafts",
        json={
            "revision": generated["revision"],
            "source_sha256": generated["source_sha256"],
            "plan_sha256": generated["plan_sha256"],
            "ir": ir,
        },
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["origin_ir"] == ir
    assert client.get(base + "/pipeline").json()["ir"] == state["ir"]


def test_resume_archived_draft_preserves_manual_source_snapshot_and_pipeline(client):
    project, path, draft, _, original = enter(client)
    source = draft["source"] + "\n# independent work\n"
    archived = client.post(
        path + f"/{draft['id']}/exit",
        json={"revision": draft["revision"], "action": "save_snapshot", "source": source},
    ).json()
    snapshots = client.get(path + f"/{draft['id']}/snapshots").json()
    body = {"revision": archived["revision"]}
    resumed = client.post(path + f"/{draft['id']}/resume", json=body)
    assert resumed.status_code == 201, resumed.text
    assert resumed.json()["id"] != draft["id"]
    assert client.get(path + f"/{draft['id']}").json() == archived
    assert resumed.json()["source"] == source
    assert resumed.json()["baseline_source"] == draft["baseline_source"]
    assert client.get(path + f"/{draft['id']}/snapshots").json() == snapshots
    assert client.get(f"/api/v1/projects/{project['id']}/pipeline").json()["ir"] == original
    assert client.post(path + f"/{draft['id']}/resume", json=body).status_code == 409
