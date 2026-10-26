"""Actual regression source evidence, bounded output and binary compatibility."""

import pytest
from test_projects_datasets import configure, upload
from test_task_targets import regression


def source(client, data=b"x,y\n1,2\n2,4\n3,6\n4,\n", target=True):
    project = regression(client)
    dataset = upload(client, project, data).json()
    if target:
        response = configure(client, project, target_column="y")
        assert response.status_code == 200, response.text
        dataset = response.json()
    return project, dataset


def profile(client, project, dataset, **params):
    return client.get(
        f"/api/v1/projects/{project['id']}/dataset/profile",
        params={"dataset_id": dataset["id"], "revision": dataset["revision"], **params},
    )


def test_regression_profile_stats_histogram_and_pairs(client):
    project, dataset = source(client)
    before = client.get(f"/api/v1/projects/{project['id']}/pipeline").json()
    response = profile(client, project, dataset, feature="x")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data == profile(client, project, dataset, feature="x").json()
    assert data["task"] == "regression" and data["population"] == "full_source"
    assert data["source_integrity"] == "verified" and data["revision"] == dataset["revision"]
    assert data["row_count"] == 4
    target = data["target"]
    assert (target["observed_count"], target["missing_count"], target["distinct_count"]) == (
        3,
        1,
        3,
    )
    numeric = target["numeric"]
    assert numeric["mean"] == numeric["median"] == 4
    assert numeric["standard_deviation"] == 2
    assert (numeric["minimum"], numeric["q1"], numeric["q3"], numeric["maximum"]) == (2, 3, 5, 6)
    assert sum(bin["count"] for bin in numeric["histogram"]) == 3
    assert len(numeric["histogram"]) <= 10
    relation = data["relationship"]
    assert relation["paired_rows"] == 3 and relation["missing_pair_rows"] == 1
    assert relation["pearson"] == pytest.approx(1)
    assert relation["points"] == [{"x": 1.0, "y": 2.0}, {"x": 2.0, "y": 4.0}, {"x": 3.0, "y": 6.0}]
    assert "classes" not in target and "positive_class" not in target
    assert client.get(f"/api/v1/projects/{project['id']}/pipeline").json() == before


@pytest.mark.parametrize("values,constant", [("5\n5\n5", True), ("0\n1\n0", False)])
def test_constant_and_two_valued_numeric_targets(client, values, constant):
    data = ("x,y\n" + "\n".join(f"{i},{v}" for i, v in enumerate(values.split("\n")))).encode()
    project, dataset = source(client, data)
    result = profile(client, project, dataset).json()
    assert result["target"]["constant"] is constant
    assert sum(b["count"] for b in result["target"]["numeric"]["histogram"]) == 3
    if constant:
        assert result["relationship"]["pearson"] is None
        assert "constant" in result["relationship"]["correlation_unavailable_reason"].lower()


def test_no_target_is_contextual_and_invalid_target_stays_rejected(client):
    project, dataset = source(client, b"x,y\n1,\n2,\n3,\n", target=False)
    result = profile(client, project, dataset)
    assert result.status_code == 200
    assert result.json()["target"] is None and result.json()["relationship"] is None
    assert configure(client, project, target_column="y").status_code == 422


def test_scatter_sampling_is_deterministic_and_bounded(client):
    data = ("x,y\n" + "\n".join(f"{i},{i * 2}" for i in range(1001))).encode()
    project, dataset = source(client, data)
    a = profile(client, project, dataset, feature="x").json()
    b = profile(client, project, dataset, feature="x").json()
    assert a == b
    relation = a["relationship"]
    assert relation["paired_rows"] == 1001 and len(relation["points"]) == 200
    assert relation["points"][0] == {"x": 0.0, "y": 0.0}
    assert relation["points"][-1] == {"x": 1000.0, "y": 2000.0}
    assert relation["pearson"] == pytest.approx(1)


@pytest.mark.parametrize(
    "rows,paired,missing,reason",
    [("1,1\n,2\n3,\n", 1, 2, "two"), ("1,1\n1,2\n1,3\n", 3, 0, "constant")],
)
def test_correlation_unavailable_reasons_and_missing_pair_union(
    client, rows, paired, missing, reason
):
    project, dataset = source(client, ("x,y\n" + rows).encode())
    response = profile(client, project, dataset, feature="x")
    assert response.status_code == 200, response.text
    relation = response.json()["relationship"]
    assert (relation["paired_rows"], relation["missing_pair_rows"]) == (paired, missing)
    assert (
        relation["pearson"] is None and reason in relation["correlation_unavailable_reason"].lower()
    )


def test_profile_uses_exact_verified_buffer_and_rejects_corruption(client, settings, monkeypatch):
    from mlstudio.codegen import workload_runtime

    project, dataset = source(client)
    path = settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    original = workload_runtime.read_verified_bytes

    def verified_then_changed(*args):
        data = original(*args)
        path.write_bytes(b"x,y\n99,999\n")
        return data

    monkeypatch.setattr(workload_runtime, "read_verified_bytes", verified_then_changed)
    result = profile(client, project, dataset)
    assert result.status_code == 200 and result.json()["target"]["numeric"]["mean"] == 4
    corrupted = profile(client, project, dataset)
    assert corrupted.status_code == 409
    assert str(settings.home) not in corrupted.text and "999" not in corrupted.text


def test_size_limit_invalid_features_and_pagination(client, settings):
    names = [f"measure_{i}" for i in range(25)]
    data = (
        ",".join(names + ["y"])
        + "\n"
        + "\n".join(",".join(str(row + i) for i in range(25)) + f",{row * 2}" for row in range(3))
    ).encode()
    project, dataset = source(client, data)
    a = profile(client, project, dataset).json()
    b = profile(client, project, dataset, offset=20).json()
    assert a["numeric_feature_count"] == 25
    assert len(a["feature_options"]) == 20 and len(b["feature_options"]) == 5
    assert b["feature_options"][0]["name"] == names[20]
    assert profile(client, project, dataset, feature="not present").status_code == 422
    assert profile(client, project, dataset, feature="y").status_code == 422
    settings.max_csv_upload_bytes = len(data) - 1
    assert profile(client, project, dataset).status_code == 413


def test_replacement_and_late_revision_changes_reject_stale_evidence(client, monkeypatch):
    from mlstudio.services import regression_profiles

    project, dataset = source(client)
    original = regression_profiles.build_regression_profile

    def changed(*args):
        result = original(*args)
        client.patch(f"/api/v1/projects/{project['id']}", json={"name": "Concurrent edit"})
        return result

    monkeypatch.setattr(regression_profiles, "build_regression_profile", changed)
    assert profile(client, project, dataset).status_code == 409
    monkeypatch.setattr(regression_profiles, "build_regression_profile", original)
    replacement = upload(client, project, b"x,y\n4,8\n5,10\n", expected=dataset["id"]).json()
    assert profile(client, project, dataset).status_code == 409
    fresh = profile(client, project, replacement)
    assert fresh.status_code == 200 and fresh.json()["target"] is None


@pytest.mark.parametrize("rows", ["1,yes\n2,no\n", "1,true\n2,false\n"])
def test_invalid_nonnumeric_target_contract(client, rows):
    project, dataset = source(client, ("x,y\n" + rows).encode(), target=False)
    assert configure(client, project, target_column="y").status_code == 422
    assert profile(client, project, dataset).json()["target"] is None


def test_precision_and_extreme_ranges_are_unavailable_without_invalid_json(client):
    project, dataset = source(client, b"x,y\n1,18014398509481984\n2,36028797018963968\n")
    result = profile(client, project, dataset).json()
    assert result["target"]["numeric"]["unavailable_reason"]
    assert result["relationship"]["points"] == []
    assert result["relationship"]["correlation_unavailable_reason"]
    project, dataset = source(client, b"x,y\n-1e308,-1e308\n1e308,1e308\n")
    result = profile(client, project, dataset).json()
    assert result["relationship"]["pearson"] == pytest.approx(1)
    assert result["relationship"]["points"] == []
    assert "precision" in result["relationship"]["scatter_unavailable_reason"]
