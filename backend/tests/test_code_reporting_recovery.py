"""Targeted new-draft execution and non-destructive legacy reporting recovery."""

import ast

import pytest
from test_code_evaluation import enter_generated, execute
from test_regression_runs import ready_regression
from test_runs import ready

from mlstudio.models import CodeDraft


@pytest.mark.parametrize(
    "setup,task", [(ready, "binary_classification"), (ready_regression, "regression")]
)
def test_unmodified_new_draft_reports_end_to_end(client, settings, setup, task):
    settings.code_execution_enabled = True
    base, draft, preview = enter_generated(client, setup)
    assert "from mlstudio_runtime import" in draft["source"]
    run, result = execute(client, base + "/code-runs", draft, draft["source"])
    assert result["status"] == "available" and result["report"]["evaluation"]["task"] == task
    assert "from mlstudio_runtime import" not in preview["source"]
    assert client.get(base + "/code").json()["source"] == preview["source"]
    if task == "binary_classification":
        assert len(result["report"]["evaluation"]["confusion_matrix"]["values"]) == 2
    else:
        assert set(result["report"]["evaluation"]["metrics"]) == {"mae", "mse", "rmse", "r2"}
    assert run["source"] == draft["source"]


def test_legacy_recovery_is_reviewed_guarded_and_preserves_edits_and_history(client, settings):
    settings.code_execution_enabled = True
    base, draft, preview = enter_generated(client, ready_regression)
    # Represent a persisted pre-2B draft. Never mutate a real user's workspace.
    with client.app.state.session_factory() as session:
        session.execute(
            CodeDraft.__table__.update()
            .where(CodeDraft.id == draft["id"])
            .values(
                baseline_source=preview["source"],
                source=preview["source"],
                baseline_sha256=preview["source_sha256"],
            )
        )
        session.commit()
    path = base + "/code-drafts/" + draft["id"]
    draft = client.get(path).json()
    old, missing = execute(client, base + "/code-runs", draft, draft["source"])
    assert missing["status"] == "not_reported"
    draft = client.get(path).json()
    original = draft["source"] + "\n# Keep my manual notes exactly.\n"
    body = {"revision": draft["revision"], "source": original}
    proposal = client.post(path + "/reporting-proposal", json=body)
    assert proposal.status_code == 200, proposal.text
    proposed = proposal.json()
    assert proposed["status"] == "ready"
    assert proposed["proposed_source"].endswith("# Keep my manual notes exactly.\n")
    assert "report_regression" in proposed["diff"]
    assert client.get(path).json() == draft  # Preview/cancel never writes.
    saved = client.patch(path, json={**body, "source": proposed["proposed_source"]})
    assert saved.status_code == 200, saved.text
    assert client.patch(path, json=body).status_code == 409
    recovered = saved.json()
    assert recovered["baseline_source"] == draft["baseline_source"]
    assert recovered["origin_ir"] == draft["origin_ir"]
    present = client.post(
        path + "/reporting-proposal",
        json={
            "revision": recovered["revision"],
            "source": recovered["source"],
        },
    ).json()
    assert present["status"] == "present" and present["proposed_source"] is None
    manual = client.post(
        path + "/reporting-proposal",
        json={
            "revision": recovered["revision"],
            "source": original.replace("predictions", "renamed"),
        },
    ).json()
    assert manual["status"] == "manual" and manual["proposed_source"] is None
    assert "report_regression" in manual["example"]
    reindented = "\n".join(
        "    " + line if line.startswith("        ") else line for line in original.split("\n")
    )
    assert ast.dump(ast.parse(reindented)) == ast.dump(ast.parse(original))
    formatting = client.post(
        path + "/reporting-proposal",
        json={
            "revision": recovered["revision"],
            "source": reindented,
        },
    ).json()
    if formatting["status"] == "ready":
        ast.parse(formatting["proposed_source"])
    _, evidence = execute(client, base + "/code-runs", recovered, recovered["source"])
    assert evidence["status"] == "available"
    assert client.get(base + f"/code-runs/{old['id']}/evaluation").json() == missing
    assert client.get(path).json()["source"] == recovered["source"]
