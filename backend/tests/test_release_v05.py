"""Small complete visual release journeys, including frozen generated execution."""

import json
import subprocess
import sys
import time
from uuid import uuid4

import pandas as pd
import pytest


@pytest.mark.parametrize(
    "task", ["binary_classification", "multiclass_classification", "regression"]
)
def test_v05_release_journey(client, settings, tmp_path, task):
    project = client.post(
        "/api/v1/projects",
        json={
            "name": "Release integration",
            "problem_statement": "Synthetic preprocessing acceptance",
            "ml_objective": task,
        },
    ).json()
    path = f"/api/v1/projects/{project['id']}"
    rows = [
        {
            "record_id": i,
            "income": "-" if i % 7 == 0 else str(100 + i * 3),
            "city": ["A", "B", "C"][i % 3],
            "date": None if i % 8 == 0 else f"2024-{i % 12 + 1:02d}-15",
            "label": i * 0.5
            if task == "regression"
            else ["a", "b", "c"][i % 3]
            if task == "multiclass_classification"
            else ["no", "yes"][i % 2],
        }
        for i in range(60)
    ]
    raw = pd.DataFrame([*rows, rows[0], rows[1]]).to_csv(index=False).encode()
    uploaded = client.post(path + "/dataset", files={"file": ("synthetic.csv", raw, "text/csv")})
    assert uploaded.status_code == 201, uploaded.text
    dataset = uploaded.json()
    configured = client.patch(
        path + "/dataset",
        json={
            "dataset_id": dataset["id"],
            "revision": dataset["revision"],
            "target_column": "label",
        },
    ).json()
    profile = client.get(
        path + "/dataset/profile",
        params={"dataset_id": dataset["id"], "revision": configured["revision"]},
    )
    assert profile.status_code == 200 and profile.json()["population"] == "full_source"
    state = client.get(path + "/pipeline").json()
    ir = state["ir"]

    def ref(name):
        return {"kind": "reference", "name": name}

    def column(name):
        return {"kind": "column", "name": name}

    ir.update(
        {
            "cleaning": {
                "version": "cleaning-v1",
                "steps": [
                    {
                        "id": "tokens",
                        "kind": "normalize",
                        "column": "income",
                        "tokens": ["-"],
                        "trim": True,
                        "case_sensitive": True,
                    },
                    {
                        "id": "numeric",
                        "kind": "convert",
                        "column": "income",
                        "destination": "continuous",
                        "invalid": "reject",
                    },
                    {
                        "id": "dates",
                        "kind": "datetime_fill",
                        "column": "date",
                        "value": "2020-01-01T00:00:00Z",
                        "policy": {"naive": "utc"},
                    },
                    {
                        "id": "population",
                        "kind": "filter",
                        "condition": {
                            "kind": "call",
                            "operation": "less",
                            "arguments": [column("record_id"), {"kind": "literal", "value": 57}],
                            "parameters": {},
                        },
                        "keep": "matches",
                    },
                    {
                        "id": "dedupe",
                        "kind": "deduplicate",
                        "columns": ["record_id"],
                        "keep": "first",
                    },
                ],
            },
            "temporal": {
                "version": "temporal-v1",
                "sources": {"date": {"format": "ISO8601", "naive": "utc", "invalid": "reject"}},
                "features": [
                    {
                        "name": "month",
                        "expression": {
                            "kind": "call",
                            "operation": "month",
                            "arguments": [column("date")],
                            "parameters": {},
                        },
                    }
                ],
            },
            "derived": {
                "version": "derived-v1",
                "features": [
                    {
                        "name": "adjusted",
                        "expression": {
                            "kind": "call",
                            "operation": "add",
                            "arguments": [column("income"), ref("month")],
                            "parameters": {},
                        },
                    },
                    {"name": "constant", "expression": {"kind": "literal", "value": 1}},
                ],
            },
            "imputation": {
                "version": "imputation-v1",
                "columns": {
                    "adjusted": {
                        "rules": [{"strategy": "mean", "group_by": ["city"]}],
                        "fallback": {"strategy": "mean"},
                    }
                },
            },
            "feature_engineering": {
                "version": "feature-engineering-v1",
                "features": [
                    {"name": "logged", "source": "adjusted", "method": "log1p"},
                    {
                        "name": "quantile",
                        "source": "logged",
                        "method": "quantile",
                        "quantiles": 20,
                        "distribution": "uniform",
                    },
                    {
                        "name": "city_grouped",
                        "source": "city",
                        "method": "rare",
                        "min_count": 2,
                        "min_frequency": None,
                        "rare_label": "Other",
                        "unknown": "rare",
                    },
                ],
            },
            "outlier_treatment": {
                "version": "outlier-treatment-v1",
                "features": [
                    {
                        "name": "capped",
                        "source": "quantile",
                        "indicator": "is_outlier",
                        "multiplier": 1.5,
                        "tails": "both",
                        "missing": "preserve",
                        "invalid": "reject",
                    }
                ],
            },
            "feature_selection": {
                "version": "feature-selection-v1",
                "method": "variance_threshold",
                "stage": "post_preprocessing",
                "features": ["capped", "constant"],
                "threshold": 0,
            },
            "model": {"type": "ridge" if task == "regression" else "logistic_regression"},
            "split": {
                "test_size": 0.25,
                "random_seed": 17,
                **({"stratify": True} if task != "regression" else {}),
            },
        }
    )
    if task == "binary_classification":
        ir["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
    ir["features"] = {
        name: {"included": False, "operations": []}
        for name in [
            "record_id",
            "income",
            "city",
            "date",
            "month",
            "adjusted",
            "logged",
            "quantile",
        ]
    }
    ir["features"].update(
        {
            "capped": {"included": True, "operations": [{"type": "scale", "method": "standard"}]},
            "constant": {"included": True, "operations": []},
            "is_outlier": {"included": True, "operations": []},
            "city_grouped": {
                "included": True,
                "operations": [{"type": "encode", "method": "one_hot"}],
            },
        }
    )
    preview = client.post(
        path + "/pipeline/temporal-preview", json={"revision": state["revision"], "ir": ir}
    ).json()
    assert not preview["errors"], preview
    assert not {"quantile", "capped", "is_outlier"} & {c["name"] for c in preview["columns"]}
    saved = client.patch(path + "/pipeline", json={"revision": state["revision"], "ir": ir}).json()
    assert saved["configuration_ready"], saved["issues"]
    assert client.get(path + "/pipeline").json()["ir"] == saved["ir"]
    code = client.get(path + "/code").json()
    assert code["ready"], code["issues"]
    request = {
        "request_id": str(uuid4()),
        "expected_revision": code["revision"],
        "expected_source_sha256": code["source_sha256"],
        "expected_plan_sha256": code["plan_sha256"],
    }
    admitted = client.post(path + "/runs", json=request)
    assert admitted.status_code == 202, admitted.text
    run_id = admitted.json()["id"]
    deadline = time.monotonic() + 60
    while True:
        run = client.get(path + f"/runs/{run_id}").json()
        if run["state"] in {"SUCCEEDED", "FAILED"}:
            break
        assert time.monotonic() < deadline, "Release Run timeout"
        time.sleep(0.1)
    assert run["state"] == "SUCCEEDED", run.get("failure")
    assert run["result"]["population"]["source"] == 62
    assert run["result"]["population"]["eligible"] == 57
    assert run["result"]["metrics"]
    assert client.get(path + f"/runs/{run_id}/code").json()["source"] == code["source"]
    directory = settings.home / "projects" / project["id"] / "runs" / run_id
    script = directory / "generated_run.py"
    assert script.read_text(encoding="utf-8") == code["source"]
    source = settings.home / "projects" / project["id"] / "datasets" / dataset["id"] / "source.csv"
    assert source.read_bytes() == raw
    repeated_model, repeated_result = tmp_path / "repeated.joblib", tmp_path / "repeated.json"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--dataset",
            str(source),
            "--model",
            str(repeated_model),
            "--result",
            str(repeated_result),
        ],
        check=True,
        timeout=40,
    )
    repeated = json.loads(repeated_result.read_text())
    assert repeated["metrics"] == pytest.approx(run["result"]["metrics"])
    loader = tmp_path / "release_inference.py"
    loader.write_text(INFERENCE, encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(loader),
            str(script),
            str(directory / "model.joblib"),
            str(repeated_model),
            str(source),
            task,
        ],
        check=True,
        timeout=40,
    )


INFERENCE = """
import importlib.util, sys, joblib, pandas as pd, numpy as np
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
class BlockBackend:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('mlstudio'): raise ImportError('backend unavailable')
sys.meta_path.insert(0, BlockBackend())
spec=importlib.util.spec_from_file_location('frozen',sys.argv[1])
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
a,b=joblib.load(sys.argv[2]),joblib.load(sys.argv[3])
source=pd.read_csv(sys.argv[4])
clean=m.CleaningFeatures(m.CLEANING_ROW_CONFIG).transform(source)
expanded=m.DerivedFeatures(m.DERIVED_CONFIG).transform(m.TemporalFeatures(m.TEMPORAL_CONFIG).transform(clean))
selected,_=m.cleaning_select(expanded,m.CLEANING_CONFIG)
stratify=selected.label if sys.argv[5]!='regression' else None
train,_=train_test_split(selected,test_size=.25,random_state=17,stratify=stratify)
imputer=a.named_steps['advanced_imputation']
assert np.isclose(imputer.statistics_['adjusted'][-1],train.adjusted.mean())
pos=[name for name,_ in a.steps].index('outliers')
before=Pipeline(a.steps[:pos]).transform(source.loc[train.index])
q1,q3=np.quantile(before['quantile'],[.25,.75])
np.testing.assert_allclose(a.named_steps['outliers'].fences_['capped'],[q1-1.5*(q3-q1),q3+1.5*(q3-q1)])
contract=a.schema_contract_
assert set(c['name'] for c in contract['raw']['raw_inputs'])=={'income','city','date'}
selection=a.named_steps['preprocessor'].preprocessor_
assert selection.variances_['constant']==0 and 'constant' not in selection.selected_features_
assert contract['estimator']['feature_count']==a.named_steps['model'].n_features_in_
assert a.schema_contract_==b.schema_contract_
raw=pd.DataFrame({'income':['-', '250','250'], 'city':['new','A','A'],
    'date':[None,'2024-12-15','2024-12-15'], 'logged':[999]*3, 'label':['shadow']*3})
before_fences=dict(a.named_steps['outliers'].fences_)
predictions=a.predict(raw)
assert len(predictions)==3 and predictions[1]==predictions[2]
individual=np.concatenate([a.predict(raw.iloc[[i]]) for i in range(len(raw))])
if sys.argv[5]=='regression': np.testing.assert_allclose(predictions,individual)
else: np.testing.assert_array_equal(predictions,individual)
if sys.argv[5]=='regression': np.testing.assert_allclose(predictions,b.predict(raw))
else: np.testing.assert_array_equal(predictions,b.predict(raw))
assert before_fences==a.named_steps['outliers'].fences_
try: a.predict(raw.drop(columns='income'))
except ValueError as error: assert 'income' in str(error)
else: raise AssertionError('missing raw input accepted')
"""
