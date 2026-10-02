import pandas as pd
import pytest

from mlstudio.models import Dataset, Project
from mlstudio.services.profiles import correlations, frequencies, numeric_profile


def setup_source(client, content):
    project = client.post(
        "/api/v1/projects", json={"name": "EDA", "problem_statement": "Understand source."}
    ).json()
    path = f"/api/v1/projects/{project['id']}"
    uploaded = client.post(path + "/dataset", files={"file": ("data.csv", content, "text/csv")})
    assert uploaded.status_code == 201, uploaded.text
    return path, uploaded.json()


def profile(client, path, source, offset=0):
    return client.get(
        path + "/dataset/profile",
        params={"dataset_id": source["id"], "revision": source["revision"], "offset": offset},
    )


def test_source_profile_facts_and_target(client):
    path, source = setup_source(
        client, b"id,x,y,group,label\n1,1,2,a,yes\n2,2,4,b,no\n3,3,6,a,yes\n4,,8,c,\n4,,8,c,\n"
    )
    selected = client.patch(
        path + "/dataset",
        json={"dataset_id": source["id"], "revision": source["revision"], "target_column": "label"},
    ).json()
    result = profile(client, path, selected)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data == profile(client, path, selected).json()
    assert data["population"] == "full_source"
    assert data["dataset_id"] == selected["id"] and data["revision"] == selected["revision"]
    assert data["row_count"] == 5 and data["column_count"] == 5 and data["feature_count"] == 4
    assert data["missing_cells"] == 4 and data["missing_percentage"] == 16
    assert data["duplicate_rows"] == 1 and data["duplicate_percentage"] == 20
    target = data["target"]
    assert target["missing_count"] == 2 and target["non_missing_count"] == 3
    assert [(item["value"], item["count"]) for item in target["classes"]] == [("yes", 2), ("no", 1)]
    assert target["majority_percentage"] == pytest.approx(200 / 3)
    x = data["columns"][1]
    assert x["missing_percentage"] == 40
    assert x["numeric"]["mean"] == 2 and x["numeric"]["standard_deviation"] == 1
    assert x["numeric"]["q1"] == 1.5 and x["numeric"]["q3"] == 2.5
    assert sum(b["count"] for b in x["numeric"]["histogram"]) == 3
    matrix = data["correlation"]
    assert "label" not in matrix["columns"]
    xi, yi = matrix["columns"].index("x"), matrix["columns"].index("y")
    assert matrix["values"][xi][yi] == pytest.approx(1)
    assert matrix["pair_counts"][xi][yi] == 3


@pytest.mark.parametrize(
    "labels,expected",
    [
        (
            ["9007199254740992", "9007199254740993"],
            [
                {"value_type": "integer", "value": "9007199254740992"},
                {"value_type": "integer", "value": "9007199254740993"},
            ],
        ),
        (
            ["-9007199254740992", "-9007199254740993"],
            [
                {"value_type": "integer", "value": "-9007199254740992"},
                {"value_type": "integer", "value": "-9007199254740993"},
            ],
        ),
        (["True", "False"], [True, False]),
        (["1.5", "2.5"], [1.5, 2.5]),
        (["A", "B"], ["A", "B"]),
    ],
)
def test_target_profile_preserves_scalar_types(client, labels, expected):
    path, source = setup_source(client, ("target\n" + "\n".join(labels) + "\n").encode())
    source = client.patch(
        path + "/dataset",
        json={
            "dataset_id": source["id"],
            "revision": source["revision"],
            "target_column": "target",
        },
    ).json()
    data = profile(client, path, source).json()
    assert [item["value"] for item in data["target"]["classes"]] == expected
    assert [item["percentage"] for item in data["target"]["classes"]] == [50, 50]


def test_no_target_all_missing_constant_and_overrides(client):
    path, source = setup_source(
        client, b"empty,constant,date,word\n,5,2025-01-01,a\n,5,2025-01-02,b\n,5,2025-01-03,c\n"
    )
    data = profile(client, path, source).json()
    assert data["target"] is None
    assert data["columns"][0]["missing_percentage"] == 100
    assert data["columns"][0]["numeric"]["histogram"] == []
    assert data["columns"][1]["numeric"]["histogram"] == [{"lower": 5.0, "upper": 5.0, "count": 3}]
    assert data["columns"][1]["numeric"]["standard_deviation"] == 0
    assert data["columns"][2]["numeric"] is None
    assert data["correlation"]["unavailable_reason"]
    changed = client.patch(
        path + "/dataset",
        json={
            "dataset_id": source["id"],
            "revision": source["revision"],
            "semantic_overrides": {"constant": "categorical", "word": "identifier"},
        },
    ).json()
    assert profile(client, path, source).status_code == 409
    fresh = profile(client, path, changed).json()
    assert fresh["columns"][1]["numeric"] is None
    assert fresh["columns"][1]["frequencies"][0]["count"] == 3
    assert fresh["columns"][3]["identifier"]


def test_histogram_quartiles_and_boxplot_outliers():
    data = numeric_profile(pd.Series([1, 2, 3, 4, 100, None])).model_dump()
    assert data["mean"] == 22
    assert (data["q1"], data["median"], data["q3"]) == (2, 3, 4)
    assert (data["lower_whisker"], data["upper_whisker"], data["outlier_count"]) == (1, 4, 1)
    assert len(data["histogram"]) == 10
    assert data["histogram"][0]["count"] == 4 and data["histogram"][-1]["count"] == 1


@pytest.mark.parametrize("values", [[0, 0, 0, 100], [0, 1, 1, 100], [0, 100, 100, 100]])
def test_skewed_small_sample_whiskers_enclose_interpolated_box(values):
    data = numeric_profile(pd.Series(values))
    assert data.lower_whisker <= data.q1 <= data.median <= data.q3 <= data.upper_whisker
    assert data.outlier_count == 1
    assert data.upper_whisker > data.lower_whisker


@pytest.mark.parametrize(
    "values",
    [
        [9007199254740992, 9007199254740993],
        [-9007199254740992, -9007199254740993],
        [9223372036854775808, 9223372036854775809],
        [100000000000000000000, 100000000000000000001],
    ],
)
def test_nullable_unsafe_integer_classes_survive_ingestion_preview_and_profile(client, values):
    content = f"label,row\n{values[0]},1\n{values[1]},2\n{values[0]},3\n,4\n".encode()
    path, source = setup_source(client, content)
    expected = [{"value_type": "integer", "value": str(value)} for value in values]
    assert source["columns"][0]["unique_count"] == 2
    assert source["preview"] == [[expected[0], 1], [expected[1], 2], [expected[0], 3], [None, 4]]
    response = client.patch(
        path + "/dataset",
        json={
            "dataset_id": source["id"],
            "revision": source["revision"],
            "target_column": "label",
        },
    )
    assert response.status_code == 200, response.text
    selected = response.json()
    assert selected["target_classes"] == expected
    target = profile(client, path, selected).json()["target"]
    assert [item["value"] for item in target["classes"]] == expected
    assert [item["count"] for item in target["classes"]] == [2, 1]
    assert target["missing_count"] == 1
    assert target["majority_percentage"] == pytest.approx(200 / 3)
    assert client.get(path + "/dataset").json()["preview"] == source["preview"]


def test_frequency_bound_tie_order_and_truncated_labels():
    series = pd.Series(["z"] * 3 + ["a"] * 3 + [f"cat{i}" for i in range(20)] + [None])
    top, other = frequencies(series, 10)
    assert [item.value for item in top[:2]] == ["z", "a"]
    assert len(top) == 10 and other == 12
    assert sum(item.count for item in top) + other == 26
    long, _ = frequencies(pd.Series(["s" * 200]), 10)
    assert long[0].label_truncated and len(long[0].value) == 120


def test_bounded_profile_pages_and_high_cardinality(client):
    names = [f"c{i}" for i in range(25)]
    content = (
        ",".join(names)
        + "\n"
        + "\n".join(",".join(f"v{row}" for _ in names) for row in range(30))
        + "\n"
    )
    path, source = setup_source(client, content.encode())
    first = profile(client, path, source).json()
    last = profile(client, path, source, 20).json()
    assert len(first["columns"]) == 20 and len(last["columns"]) == 5
    assert first["columns"][0]["high_cardinality"]
    assert first["columns"][0]["distinct_count"] == 30
    assert profile(client, path, source, -1).status_code == 422


def test_replaced_dataset_and_metadata_revisions_reject_stale_profile(client):
    path, source = setup_source(client, b"x,y\n1,2\n2,4\n3,6\n")
    replacement = client.post(
        path + "/dataset",
        files={"file": ("new.csv", b"x,y\n3,9\n4,16\n5,25\n")},
        data={"expected_dataset_id": source["id"]},
    ).json()
    assert profile(client, path, source).status_code == 409
    assert profile(client, path, replacement).json()["dataset_id"] == replacement["id"]
    client.patch(path, json={"name": "Changed"})
    assert profile(client, path, replacement).status_code == 409


def test_correlations_bound_and_null_pairs():
    frame = pd.DataFrame({f"x{i}": [1.0, 2.0, 3.0] for i in range(15)})
    frame["x1"] = [1.0, 1.0, 1.0]
    frame["x2"] = [None, None, 3.0]
    dataset = Dataset(
        columns=[
            {"name": name, "semantic_override": None, "inferred_semantic_type": "continuous"}
            for name in frame.columns
        ]
    )
    project = Project(target_column=None, working_pipeline=None)
    data = correlations(frame, dataset, project)
    assert len(data.columns) == 12 and data.eligible_count == 15
    assert data.values[0][1] is None and data.values[0][2] is None
    assert data.pair_counts[0][2] == 1
    assert data.values[0][3] == pytest.approx(1)


def test_unsafe_integer_and_extreme_numeric_summaries_are_explicit():
    unsafe = numeric_profile(pd.Series([9007199254740992, 9007199254740993]))
    assert unsafe.minimum.value == "9007199254740992"
    assert unsafe.unavailable_reason and unsafe.histogram == []
    extreme = numeric_profile(pd.Series([-1e308, 1e308]))
    assert extreme.unavailable_reason and extreme.mean is None


@pytest.mark.parametrize(
    "values", [[1.0, 1.0000000000000002, 1.0000000000000004], [0.0, 5e-324, 1e-323]]
)
def test_adjacent_float_histograms_preserve_all_observations(values):
    result = numeric_profile(pd.Series(values))
    assert result.unavailable_reason is None
    assert sum(bin.count for bin in result.histogram) == len(values)
    assert all(bin.lower < bin.upper for bin in result.histogram)
    assert len(result.histogram) <= 10


def test_metadata_edit_during_profiling_returns_conflict(client, monkeypatch):
    from mlstudio.services import profiles

    path, source = setup_source(client, b"x\n1\n2\n3\n")
    original = profiles.build_profile

    def change_during(*args):
        result = original(*args)
        client.patch(path, json={"name": "Concurrent change"})
        return result

    monkeypatch.setattr(profiles, "build_profile", change_during)
    assert profile(client, path, source).status_code == 409


def test_dataset_replacement_during_profiling_returns_conflict(client, monkeypatch):
    from mlstudio.services import profiles

    path, source = setup_source(client, b"x\n1\n2\n3\n")
    original = profiles.build_profile

    def replace_during(*args):
        result = original(*args)
        response = client.post(
            path + "/dataset",
            files={"file": ("replacement.csv", b"x\n4\n5\n6\n")},
            data={"expected_dataset_id": source["id"]},
        )
        assert response.status_code == 201
        return result

    monkeypatch.setattr(profiles, "build_profile", replace_during)
    assert profile(client, path, source).status_code == 409
