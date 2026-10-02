from pathlib import Path
from uuid import UUID

import numpy as np
import pandas as pd
import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_profiles import profile, setup_source

from alembic import command
from mlstudio.main import create_app
from mlstudio.models import Dataset
from mlstudio.services.profiles import adjusted_skewness, column_quality, numeric_profile
from mlstudio.services.source import infer_semantic


@pytest.mark.parametrize(
    "name,values,expected",
    [
        ("id", [1, 2, 3], "identifier"),
        ("customer_id", [1, None, 2, 3], "identifier"),
        ("user_id", ["u-a", "u-b", "u-c"], "identifier"),
        ("recordKey", ["a123", "b987", "c456"], "identifier"),
        ("identifier", [100, 101, 102], "identifier"),
        ("event", [str(UUID(int=i)) for i in range(3)], "identifier"),
        ("guid", ["{" + str(UUID(int=i)) + "}" for i in range(3)], "identifier"),
        ("event", ["{" + str(UUID(int=i)) for i in range(3)], "categorical"),
        ("id", [*range(19), 0], "identifier"),
        ("id", [*range(18), 0, 1], "continuous"),
        ("id", [1.2, 2.5, 3.9], "continuous"),
        ("id", ["a@example.com", "b@example.com", "c@example.com"], "categorical"),
        ("paid", [1, 2, 3], "continuous"),
        ("width", [1, 2, 3], "continuous"),
        ("middle", ["a", "b", "c"], "categorical"),
        ("age", [21, 22, 23, 24], "continuous"),
        ("zipcode", [10001, 10002, 10003], "continuous"),
        ("code", [1, 2, 3] * 10, "continuous"),
        ("flag", [0, 1, 0], "binary"),
        ("flag", [True, False, True], "binary"),
        ("label", ["yes", "no", None], "binary"),
        ("date", ["2025-01-01", "2025-02-01", "2025-03-01"], "datetime"),
        (
            "words",
            ["This is a sentence with enough words to be free text", "short", "other"],
            "text",
        ),
        ("opaque", [f"code-{i}" for i in range(30)], "text"),
        ("constant", [1, 1, 1], "unknown"),
        ("mostly_missing", [None] * 50 + [4], "unknown"),
        ("id", [None] * 50 + [1, 2, 3], "identifier"),
    ],
)
def test_semantic_v2_regressions(name, values, expected):
    assert infer_semantic(pd.Series(values, name=name)) == expected


@pytest.mark.parametrize("dominant,expected", [(94, False), (95, True), (96, True)])
def test_near_constant_boundary_excludes_missing(dominant, expected):
    q = column_quality(
        pd.Series(["a"] * dominant + ["b"] * (100 - dominant) + [None] * 50), "binary"
    )
    assert q["near_constant"] is expected
    assert q["dominant_percentage"] == dominant
    assert q["dominant_count"] == dominant
    assert not q["constant"]


def test_constant_all_missing_and_high_cardinality():
    assert column_quality(pd.Series([1, 1, None]), "unknown")["constant"]
    empty = column_quality(pd.Series([None] * 10), "unknown")
    assert not empty["constant"] and not empty["near_constant"]
    assert empty["dominant_count"] == 0
    assert not column_quality(pd.Series(list(range(19))), "categorical")["high_cardinality"]
    assert column_quality(pd.Series(list(range(20)) * 2), "categorical")["high_cardinality"]
    assert not column_quality(pd.Series(list(range(20)) * 3), "categorical")["high_cardinality"]


@pytest.mark.parametrize(
    "values", [[1.0, 2.0, 3.0, 4.0, 100.0], [1.0, 2.0, 3.0], [-10.0, -3.0, -1.0, 2.0]]
)
def test_adjusted_skewness_matches_pandas(values):
    skew, reason = adjusted_skewness(np.array(values))
    assert reason is None
    assert skew == pytest.approx(pd.Series(values).skew(), abs=1e-12)
    shifted, _ = adjusted_skewness(np.array(values) + 1e12)
    assert shifted == pytest.approx(skew, abs=1e-12)


@pytest.mark.parametrize("values", [[1.0], [1.0, 2.0], [5.0, 5.0, 5.0]])
def test_skewness_undefined_is_not_zero(values):
    skew, reason = adjusted_skewness(np.array(values))
    assert skew is None and reason


def test_iqr_fences_percentages_and_tiny_samples():
    n = numeric_profile(pd.Series([1, 2, 3, 4, 100, None]))
    assert n.lower_fence == -1 and n.upper_fence == 7
    assert n.outlier_count == 1 and n.outlier_percentage == 20
    constant = numeric_profile(pd.Series([7, 7, 7, None]))
    assert constant.lower_fence == constant.upper_fence == 7
    assert constant.outlier_count == 0 and constant.skewness is None
    single = numeric_profile(pd.Series([2.0]))
    assert single.outlier_count == 0 and single.standard_deviation is None
    empty = numeric_profile(pd.Series([None], dtype=float))
    assert empty.outlier_count is None and empty.outlier_percentage is None
    unsafe = numeric_profile(pd.Series([9007199254740992, 9007199254740993]))
    assert unsafe.lower_fence is None and unsafe.skewness is None


def test_quality_filters_boundedness_and_determinism(client):
    names = [f"c{i}" for i in range(25)]
    content = (
        ",".join(names)
        + "\n"
        + ",".join("1" for _ in names)
        + "\n"
        + ",".join("" for _ in names)
        + "\n"
    ).encode()
    path, source = setup_source(client, content)
    result = profile(client, path, source).json()
    assert result["quality"]["constant_count"] == 25
    assert len(result["quality"]["missing_columns"]) == 20
    assert result["quality"]["missing_column_count"] == 25
    assert result["quality"]["missing_columns"][0]["name"] == "c0"
    assert result["profile_version"] == "source-profile-v2"
    assert result == profile(client, path, source).json()
    params = {
        "dataset_id": source["id"],
        "revision": source["revision"],
        "query": "C2",
        "observation": "constant",
    }
    filtered = client.get(path + "/dataset/profile", params=params).json()
    assert filtered["filtered_column_count"] == 6
    assert len(filtered["columns"]) == 6
    assert filtered["quality"] == result["quality"]
    params["query"] = "x" * 201
    assert client.get(path + "/dataset/profile", params=params).status_code == 422
    params["query"], params["kind"] = "", "not_a_type"
    assert client.get(path + "/dataset/profile", params=params).status_code == 422


def test_override_pipeline_profile_target_refresh_and_restart(client, settings):
    path, source = setup_source(
        client, b"id,zipcode,label\n1,10001,yes\n2,10002,no\n3,10003,yes\n4,10004,no\n"
    )
    source = client.patch(
        path + "/dataset",
        json={"dataset_id": source["id"], "revision": source["revision"], "target_column": "label"},
    ).json()
    pipeline = client.get(path + "/pipeline").json()
    pipeline["ir"]["features"]["zipcode"]["operations"] = [{"type": "scale", "method": "standard"}]
    pipeline["ir"]["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
    pipeline = client.patch(
        path + "/pipeline", json={"revision": pipeline["revision"], "ir": pipeline["ir"]}
    ).json()
    source = client.get(path + "/dataset").json()
    before = profile(client, path, source).json()
    assert before["target"]["positive_class"] == {"value_type": "string", "value": "yes"}
    change = {
        "dataset_id": source["id"],
        "revision": source["revision"],
        "semantic_overrides": {"zipcode": "categorical", "label": "continuous"},
    }
    response = client.patch(path + "/dataset", json=change)
    assert response.status_code == 200
    changed = response.json()
    assert client.patch(path + "/dataset", json=change).status_code == 409
    assert profile(client, path, source).status_code == 409
    now = profile(client, path, changed).json()
    assert now["columns"][1]["numeric"] is None and now["columns"][1]["frequencies"]
    assert "zipcode" not in now["correlation"]["columns"]
    assert (
        changed["target_column"] == "label"
        and changed["target_classes"] == source["target_classes"]
    )
    recipe = client.get(path + "/pipeline").json()
    assert recipe["ir"] == pipeline["ir"]
    assert any(
        i["column"] == "zipcode" and i["code"] == "operation_incompatible" for i in recipe["issues"]
    )
    assert not any(i["scope"] == "target" for i in recipe["issues"])
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path + "/dataset").json() == changed
    # Simulate a persisted semantic-v1 detection. Refresh must preserve the override.
    with client.app.state.session_factory() as session:
        stored = session.get(Dataset, source["id"])
        stored.columns = [
            {**c, "inferred_semantic_type": "categorical", "inference_version": "semantic-v1"}
            if c["name"] == "id"
            else c
            for c in stored.columns
        ]
        session.commit()
    refreshed = client.patch(
        path + "/dataset",
        json={
            "dataset_id": changed["id"],
            "revision": changed["revision"],
            "refresh_inference": True,
        },
    ).json()
    assert refreshed["columns"][0]["inferred_semantic_type"] == "identifier"
    assert refreshed["columns"][1]["semantic_override"] == "categorical"
    assert refreshed["fingerprint"] == source["fingerprint"]
    reset = client.patch(
        path + "/dataset",
        json={
            "dataset_id": refreshed["id"],
            "revision": refreshed["revision"],
            "semantic_overrides": {"zipcode": None, "label": None},
        },
    ).json()
    assert reset["columns"][1]["effective_semantic_type"] == "continuous"
    assert profile(client, path, reset).json()["columns"][1]["numeric"]
    invalid = client.patch(
        path + "/dataset",
        json={
            "dataset_id": reset["id"],
            "revision": reset["revision"],
            "semantic_overrides": {"zipcode": "binary"},
            "target_column": "zipcode",
        },
    )
    assert invalid.status_code == 422  # Four labels do not become binary through annotation.


def test_stale_schema_and_live_migration_retry(settings):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = settings
    with TestClient(create_app(settings)) as app:
        response = app.get("/api/v1/projects")
        assert response.status_code == 503
        assert "Current revision: none" in response.json()["detail"]
        assert "python -m alembic upgrade head" in response.json()["detail"]
        command.upgrade(config, "0002_project_dataset")
        assert "0002_project_dataset" in app.get("/api/v1/projects").json()["detail"]
        command.upgrade(config, "head")
        command.check(config)
        assert app.get("/api/v1/projects").status_code == 200


def test_multiple_revision_heads_and_no_mutation(monkeypatch):
    from mlstudio.db import revision

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('a'), ('b')"))
        monkeypatch.setattr(revision, "required_heads", lambda: ("b", "a"))
        assert revision.migration_message(connection) is None
        monkeypatch.setattr(revision, "required_heads", lambda: ("a",))
        assert "migration required" in revision.migration_message(connection)
        assert connection.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 2
    engine.dispose()


def test_healthy_schema_check_runs_once(client, monkeypatch):
    from mlstudio.db import session

    original = session.migration_message
    calls = []

    def check(connection):
        calls.append(1)
        return original(connection)

    monkeypatch.setattr(session, "migration_message", check)
    client.get("/api/v1/projects")
    client.get("/api/v1/projects")
    assert len(calls) == 1
