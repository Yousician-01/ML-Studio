"""Train-only feature engineering, explicit domains and portable fitted state."""

import numpy as np
import pandas as pd
import pytest


def step(method, source="x", name="out", **kwargs):
    return {"method": method, "source": source, "name": name, **kwargs}


def transformer(*steps):
    from mlstudio.feature_engineering_runtime_v1 import EngineeringFeatures
    from mlstudio.feature_engineering_schemas import EngineeringConfig

    config = EngineeringConfig(features=list(steps)).model_dump(mode="json")
    return EngineeringFeatures(config)


def test_math_reuses_derived_domains_and_preserves_missing():
    frame = pd.DataFrame({"x": [0.0, 1.0, -1.0, -2.0, np.nan]})
    for method, invalid in [("log", 3), ("log1p", 2), ("sqrt", 2), ("reciprocal", 1)]:
        result = transformer(step(method, invalid="coerce")).fit_transform(frame)
        assert result.out.isna().sum() == invalid + 1
        with pytest.raises(ValueError, match="invalid"):
            transformer(step(method)).fit_transform(frame)
    with pytest.raises(ValueError, match="finite"):
        transformer(step("sqrt")).fit_transform(pd.DataFrame({"x": [np.inf]}))

    assert transformer(step("log", invalid="coerce")).fit_transform(
        pd.DataFrame({"x": [np.inf, 0.0, 1.0]})
    ).out.isna().tolist() == [True, True, False]


def test_power_fits_only_training_and_rejects_degenerate_domains():
    train = pd.DataFrame({"x": [1.0, 2.0, 4.0, 8.0, np.nan]})
    for method in ["yeo_johnson", "box_cox"]:
        fitted = transformer(step(method)).fit(train)
        parameter = fitted.fitted_["out"].lambdas_.copy()
        result = fitted.transform(pd.DataFrame({"x": [1000.0, np.nan]}))
        assert np.isfinite(result.out.iloc[0]) and pd.isna(result.out.iloc[1])
        np.testing.assert_array_equal(parameter, fitted.fitted_["out"].lambdas_)
        with pytest.raises(ValueError, match="distinct"):
            transformer(step(method)).fit(pd.DataFrame({"x": [2.0, 2.0]}))
    with pytest.raises(ValueError, match="positive"):
        transformer(step("box_cox")).fit(pd.DataFrame({"x": [-1.0, 0.0, 1.0]}))


def test_quantiles_reproducible_small_samples_and_no_inference_refit():
    train = pd.DataFrame({"x": [1.0, 1.0, 2.0, 4.0, np.nan]})
    for distribution in ["normal", "uniform"]:
        a = transformer(step("quantile", distribution=distribution)).fit(train)
        b = transformer(step("quantile", distribution=distribution)).fit(train)
        test = pd.DataFrame({"x": [-100.0, 100.0, np.nan]})
        pd.testing.assert_frame_equal(a.transform(test), b.transform(test))
        assert a.fitted_["out"].n_quantiles_ == 4
        assert np.isfinite(a.transform(test).out.iloc[:2]).all()


def test_bins_closure_tails_duplicates_and_training_only_edges():
    fixed = transformer(step("boundaries", boundaries=[0.0, 10.0])).fit(pd.DataFrame({"x": [1.0]}))
    assert fixed.transform(pd.DataFrame({"x": [-1.0, 0.0, 10.0, 11.0, np.nan]})).out.tolist()[
        :4
    ] == ["bin_0", "bin_1", "bin_2", "bin_2"]
    for method in ["width", "quantile_bins"]:
        fitted = transformer(step(method, bins=4)).fit(pd.DataFrame({"x": [1.0, 1.0, 2.0, 2.0]}))
        assert fitted.transform(pd.DataFrame({"x": [-100.0, 100.0]})).out.notna().all()
        assert fitted.diagnostics_["out"]["actual_bins"] <= 4
    with pytest.raises(ValueError, match="boundar"):
        transformer(step("boundaries", boundaries=[1.0, 1.0]))


def test_rare_typed_categories_unknowns_missing_and_collision():
    frame = pd.DataFrame({"x": ["a", "a", "b", None]})
    fitted = transformer(step("rare", min_frequency=0.5)).fit(frame)
    result = fitted.transform(pd.DataFrame({"x": ["a", "b", "new", None]})).out
    assert result.iloc[:3].tolist() == ["a", "Other", "Other"] and pd.isna(result.iloc[3])
    with pytest.raises(ValueError, match="unknown"):
        transformer(step("rare", unknown="reject")).fit(frame).transform(
            pd.DataFrame({"x": ["new"]})
        )
    with pytest.raises(ValueError, match="collid"):
        transformer(step("rare", rare_label="a")).fit(frame)
    typed = transformer(step("rare", min_count=1, min_frequency=None)).fit(
        pd.DataFrame({"x": pd.Series([True, 1, "1"], dtype=object)})
    )
    assert len(typed.fitted_["out"]["known"]) == 3
    with pytest.raises(ValueError, match="collid"):
        transformer(step("rare", unknown="preserve")).fit(frame).transform(
            pd.DataFrame({"x": pd.Series([1, "1.0"], dtype=object)})
        )


def test_ordinal_typed_keys_unique_codes_and_unknown_policy():
    mapping = [{"value": True, "code": 1}, {"value": 1, "code": 2}, {"value": "1", "code": 3}]
    values = pd.DataFrame({"x": pd.Series([True, 1, "1", None, "new"], dtype=object)})
    result = transformer(step("ordinal", mapping=mapping, unknown="missing")).fit_transform(values)
    assert result.out.iloc[:3].tolist() == [1.0, 2.0, 3.0] and result.out.iloc[3:].isna().all()
    with pytest.raises(ValueError, match="unique"):
        transformer(step("ordinal", mapping=[mapping[0], mapping[0]]))
    assert (
        transformer(step("ordinal", mapping=mapping, unknown="code", unknown_code=-1))
        .fit_transform(values)
        .out.iloc[-1]
        == -1
    )


def test_stage_validation_preview_and_no_learned_output_fabrication(client, monkeypatch):
    from mlstudio.feature_engineering_runtime_v1 import engineering_preview, engineering_validate

    cfg = transformer(step("quantile"), step("log1p", source="month", name="month_log")).config
    engineering_validate(cfg, {"x": "numeric", "month": "numeric"}, "label")
    preview, diagnostics = engineering_preview(
        pd.DataFrame({"x": [1.0, 2.0], "month": [1.0, 2.0]}), cfg
    )
    assert "out" not in preview and "month_log" in preview
    assert diagnostics["out"]["fitted"] is True
    for bad in [
        step("sqrt", source="label"),
        step("sqrt", source="missing"),
        step("sqrt", name="x"),
        step("sqrt", source="out", name="next"),
    ]:
        with pytest.raises(ValueError):
            engineering_validate(
                {"features": [step("quantile"), bad]}, {"x": "numeric", "month": "numeric"}, "label"
            )

    from test_projects_datasets import configure, create, upload

    from mlstudio.feature_engineering_runtime_v1 import EngineeringFeatures

    def refuse_fit(*args, **kwargs):
        raise AssertionError("Preview and persistence must not fit learned transforms")

    monkeypatch.setattr(EngineeringFeatures, "fit", refuse_fit)
    project = create(client)
    upload(client, project, b"x,label\n1,yes\n2,no\n4,yes\n8,no\n")
    configure(client, project, target_column="label")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    ir = state["ir"]
    ir["feature_engineering"] = {
        "version": "feature-engineering-v1",
        "features": [
            step("log1p", name="logged"),
            step("quantile", quantiles=10, distribution="uniform"),
        ],
    }
    ir["features"].update(
        {name: {"included": True, "operations": []} for name in ["logged", "out"]}
    )
    body = {"revision": state["revision"], "ir": ir}
    response = client.post(path + "/temporal-preview", json=body)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["errors"] == []
    assert preview["feature_engineering"]["out"]["fitted"]
    assert "out" not in [c["name"] for c in preview["columns"]]
    assert next(c for c in preview["columns"] if c["name"] == "x")["values"] == [1, 2, 4, 8]
    np.testing.assert_allclose(
        next(c for c in preview["columns"] if c["name"] == "logged")["values"],
        np.log1p([1, 2, 4, 8]),
    )
    saved = client.patch(path, json=body)
    assert saved.status_code == 200, saved.text
    assert (
        client.get(path).json()["ir"]["feature_engineering"]
        == saved.json()["ir"]["feature_engineering"]
    )
    assert (
        next(c for c in saved.json()["columns"] if c["name"] == "out")["physical_dtype"]
        == "float64"
    )
    bad = saved.json()["ir"]
    bad["feature_engineering"]["features"][0]["source"] = "label"
    rejected = client.post(
        path + "/temporal-preview", json={"revision": saved.json()["revision"], "ir": bad}
    )
    assert rejected.json()["errors"]


def test_compiler_all_tasks_extensions_and_fresh_process_inference(tmp_path):
    import hashlib
    import json
    import subprocess
    import sys
    from types import SimpleNamespace

    from mlstudio.codegen.csv_runtime import parse_csv_bytes
    from mlstudio.codegen.dispatch import generate_for_version, resolve_for_version
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.source import describe_columns

    for version, task in [
        ("0.1", "binary_classification"),
        ("0.2", "regression"),
        ("0.3", "multiclass_classification"),
    ]:
        data = pd.DataFrame(
            {
                "x": np.where(np.arange(36) % 7 == 0, np.nan, np.arange(36) + 1.0),
                "group": ["a", "b", "c"] * 12,
                "date": [f"2024-{1 + i % 12:02d}-15" for i in range(36)],
                "target": np.arange(36) * 0.2
                if version == "0.2"
                else ["no", "yes"] * 18
                if version == "0.1"
                else ["a", "b", "c"] * 12,
            }
        )
        raw = data.to_csv(index=False).encode()
        frame = parse_csv_bytes(raw)
        dataset = SimpleNamespace(
            id="engineering-test",
            fingerprint="sha256:" + hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            columns=describe_columns(frame),
        )
        payload = {
            "ir_version": version,
            "dataset": {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint},
            "target": {"column": "target"},
            "features": {
                name: {"included": False, "operations": []}
                for name in ["x", "group", "date", "month", "twice"]
            },
            "split": {},
            "model": {"type": "ridge" if version == "0.2" else "logistic_regression"},
            "derived": {
                "version": "derived-v1",
                "features": [
                    {
                        "name": "twice",
                        "expression": {
                            "kind": "call",
                            "operation": "multiply",
                            "arguments": [
                                {"kind": "column", "name": "x"},
                                {"kind": "literal", "value": 2},
                            ],
                            "parameters": {},
                        },
                    }
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
                            "arguments": [{"kind": "column", "name": "date"}],
                            "parameters": {},
                        },
                    }
                ],
            },
            "feature_engineering": {
                "version": "feature-engineering-v1",
                "features": [
                    step("quantile", source="twice", name="q"),
                    step("quantile_bins", name="bins"),
                    step("rare", source="group", name="grouped"),
                    step(
                        "ordinal",
                        source="group",
                        name="ordered",
                        mapping=[
                            {"value": "a", "code": 0},
                            {"value": "b", "code": 1},
                            {"value": "c", "code": 2},
                        ],
                    ),
                    step("log1p", name="logged"),
                    step("log1p", source="month", name="month_log"),
                ],
            },
            "cleaning": {
                "version": "cleaning-v1",
                "steps": [
                    {
                        "id": "positive",
                        "kind": "validate",
                        "column": "x",
                        "check": "range",
                        "action": "reject",
                        "minimum": 0,
                    }
                ],
            },
            "imputation": {
                "version": "imputation-v1",
                "columns": {
                    "x": {
                        "rules": [{"strategy": "median"}],
                        "fallback": {"strategy": "constant", "value": 1},
                    }
                },
            },
        }
        payload["features"].update(
            {
                name: {
                    "included": True,
                    "operations": [{"type": "encode", "method": "one_hot"}]
                    if name in {"bins", "grouped"}
                    else ([{"type": "impute", "strategy": "median"}] if name == "q" else [])
                    + [{"type": "scale", "method": "standard"}],
                }
                for name in ["q", "bins", "grouped", "ordered", "logged", "month_log"]
            }
        )
        if version == "0.1":
            payload["target"]["positive_class"] = {"value_type": "string", "value": "yes"}
        else:
            payload["task"] = task
        ir = load_ir(payload, task)
        plan, issues = resolve_for_version(ir, dataset, "target", frame)
        assert plan is not None, issues
        source = generate_for_version(plan)
        assert source == generate_for_version(plan)
        assert (
            source.index("('advanced_imputation',")
            < source.index("('feature_engineering',")
            < source.index("('preprocessor',")
        )
        directory = tmp_path / version
        directory.mkdir()
        script, csv, result, model = [
            directory / name
            for name in ["generated.py", "source.csv", "result.json", "model.joblib"]
        ]
        script.write_text(source, encoding="utf-8")
        csv.write_bytes(raw)
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--dataset",
                str(csv),
                "--result",
                str(result),
                "--model",
                str(model),
            ],
            check=True,
            timeout=40,
        )
        assert json.loads(result.read_text())["status"] == "success"
        loader = directory / "predict.py"
        loader.write_text(
            "import importlib.util, sys, joblib, pandas as pd\n"
            "class BlockBackend:\n"
            " def find_spec(self, fullname, path=None, target=None):\n"
            "  if fullname.startswith('mlstudio'): raise ImportError('backend blocked')\n"
            "sys.meta_path.insert(0, BlockBackend())\n"
            "spec=importlib.util.spec_from_file_location('frozen',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "model=joblib.load(sys.argv[2]); raw=pd.read_csv(sys.argv[3]).drop(columns='target')\n"
            "assert model.predict(raw).shape == (len(raw),)\n"
            "eng=model.named_steps['feature_engineering']\n"
            "before=eng.fitted_['q'].quantiles_.copy(); model.predict(raw.iloc[:2])\n"
            "assert (before == eng.fitted_['q'].quantiles_).all()\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(loader), str(script), str(model), str(csv)], check=True, timeout=30
        )
