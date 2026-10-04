"""Source goldens, read-only preview guarantees, and isolated library compatibility."""

import ast
import hashlib
import importlib.util
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, RobustScaler, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import select
from test_projects_datasets import configure, create, upload
from test_train_configuration import experiment, save

from mlstudio.codegen.compatibility import target_supported
from mlstudio.codegen.csv_runtime import parse_csv_bytes
from mlstudio.codegen.plan import resolve
from mlstudio.codegen.render import generate, literal, scalar_value
from mlstudio.codegen.schemas import EffectiveExecutionPlan
from mlstudio.codegen.workload_runtime import (
    evaluate_predictions,
    read_verified_bytes,
    runtime_paths,
    scalar_record,
    validate_target,
    validate_training_partition,
    verify_environment,
    write_model,
    write_result,
)
from mlstudio.models import Project
from mlstudio.pipeline_schemas import PipelineIR
from mlstudio.services.source import describe_columns, parse_source
from mlstudio.services.train_validation import partition_sizes, stratified_train_counts

GOLDENS = Path(__file__).parent / "golden"
FIXED_LIBRARIES = {
    "pandas": "3.0.6",
    "numpy": "2.5.3",
    "scikit-learn": "1.9.1",
    "joblib": "1.5.3",
    "scipy": "1.18.1",
}


def prepared(model="logistic_regression", labels=None, mixed=False):
    labels = ["no", "yes"] if labels is None else labels
    frame = pd.DataFrame({"age": range(20), "target": labels * 10})
    if mixed:
        frame = frame.assign(
            income=np.arange(20) * 2.1,
            balance=np.arange(20) * 3.4,
            city=["west", "east"] * 10,
            dormant=range(20),
        )
    dataset = SimpleNamespace(
        id="11111111-1111-4111-8111-111111111111",
        fingerprint="sha256:" + "a" * 64,
        columns=describe_columns(frame),
        size_bytes=200,
    )
    # These are supported semantic configurations, not inference overrides in the renderer.
    features = {c: {"included": c != "dormant", "operations": []} for c in frame if c != "target"}
    if mixed:
        for name, strategy, scale in [
            ("age", "mean", "standard"),
            ("income", "median", "min_max"),
            ("balance", "most_frequent", "robust"),
        ]:
            features[name]["operations"] = [
                {"type": "impute", "strategy": strategy},
                {"type": "scale", "method": scale},
            ]
        features["city"]["operations"] = [
            {"type": "impute", "strategy": "most_frequent"},
            {"type": "encode", "method": "one_hot"},
        ]
        features["dormant"]["operations"] = [{"type": "encode", "method": "one_hot"}]
    ir = PipelineIR.model_validate(
        {
            "dataset": {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint},
            "target": {"column": "target", "positive_class": scalar_record(labels[1])},
            "features": features,
            "model": {"type": model},
            "split": {},
        }
    )
    return ir, dataset, frame


def plan_for(model="logistic_regression", **kwargs):
    ir, dataset, frame = prepared(model, **kwargs)
    plan, issues = resolve(ir, dataset, "target", frame)
    assert plan is not None, issues
    return plan


def golden_plan(case):
    plan = plan_for(
        case if case in {"decision_tree", "random_forest"} else "logistic_regression",
        mixed=case == "mixed",
    )
    payload = plan.model_dump()
    payload["implementation"].update(libraries=FIXED_LIBRARIES, python="3.14.2")
    if case == "l1":
        payload["model"]["parameters"].update(penalty="l1", solver="liblinear", l1_ratio=1.0)
    if case == "unstratified":
        payload["split"]["stratify"] = False
    return EffectiveExecutionPlan.model_validate(payload)


@pytest.mark.parametrize(
    "case", ["numeric", "l1", "decision_tree", "random_forest", "mixed", "unstratified"]
)
def test_source_goldens(case):
    source = generate(golden_plan(case))
    assert source.encode() == (GOLDENS / f"{case}.py.txt").read_bytes()
    ast.parse(source)
    compile(source, "generated_run.py", "exec")
    assert "\r" not in source and source.endswith("\n") and not source.endswith("\n\n")


def test_plan_determinism_and_meaningful_changes(monkeypatch):
    ir, dataset, frame = prepared(mixed=True)
    first, _ = resolve(ir, dataset, "target", frame)
    before = ir.model_dump()
    ir.features = dict(reversed(list(ir.features.items())))
    second, _ = resolve(ir, dataset, "target", frame)
    assert first.model_dump() == second.model_dump()
    monkeypatch.setenv("MLSTUDIO_HOME", "unrelated-workspace")
    monkeypatch.setenv("PYTHONHASHSEED", "111")
    random.seed(999)
    monkeypatch.setattr(time, "time", lambda: 1234567890.0)
    assert generate(first) == generate(second) == generate(first)
    assert ir.model_dump() == before
    data = first.model_dump()
    data["split"]["test_size"] = 0.3
    changed = generate(EffectiveExecutionPlan.model_validate(data))
    assert changed == generate(first).replace("test_size=0.2,", "test_size=0.3,")
    forest = plan_for("random_forest")
    data = forest.model_dump()
    data["model"]["parameters"]["n_estimators"] = 500
    assert generate(EffectiveExecutionPlan.model_validate(data)) == generate(forest).replace(
        "n_estimators=100", "n_estimators=500"
    )


@pytest.mark.parametrize(
    "labels,supported",
    [
        (["no", "yes"], True),
        ([0, 1], True),
        ([1.0, 2.0], True),
        ([True, False], True),
        ([0.1, 0.6], False),
        ([2**53, 2**53 + 1], True),
        ([2**65, 2**65 + 1], False),
    ],
)
def test_target_compatibility_and_literals(labels, supported):
    ir, dataset, frame = prepared(labels=labels)
    assert target_supported(frame.target) == supported
    plan, issues = resolve(ir, dataset, "target", frame)
    assert (plan is not None) == supported
    if supported:
        assert scalar_value(plan.target.positive_class) == labels[1]
        assert type(scalar_value(plan.target.positive_class)) is type(labels[1])
        assert "POSITIVE_CLASS = " + literal(labels[1]) in generate(plan)
    else:
        assert "target_representation" in {i.code for i in issues}


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        1,
        1.0,
        2**80,
        "1",
        "日本語",
        'a"b',
        "a'b",
        "path\\name",
        "x\nvalue",
        "x\r\nvalue",
        "\\",
    ],
)
def test_safe_literals(value):
    restored = ast.literal_eval(literal(value))
    assert restored == value and type(restored) is type(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), {1, 2}])
def test_nonliteral_rejected(value):
    with pytest.raises(ValueError):
        literal(value)


def test_awkward_names_never_identifiers():
    plan = plan_for()
    names = [
        "customer name",
        "customer-id",
        "class",
        "import",
        'a"b',
        "a'b",
        "path\\name",
        "日本語",
        "x'); __import__('os').system('bad'); #",
    ]
    payload = plan.model_dump()
    payload["features"] = [{**payload["features"][0], "name": name} for name in names]
    source = generate(EffectiveExecutionPlan.model_validate(payload))
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Name) and node.id in names for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval", "__import__"}
        for node in ast.walk(tree)
    )
    assert "mlstudio." not in source


def imported_source(tmp_path, plan):
    path = tmp_path / "preview_module.py"
    path.write_text(generate(plan), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("preview_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # Import-only: the main guard prevents workload execution.
    return module


@pytest.mark.parametrize(
    "content",
    [
        b"x,y\n1,a\n2,b\n",
        b"\xef\xbb\xbfx,y\n1,a\n2,b\n",
        b"x,y\n,a\nNA,b\nNaN,a\nnull,b\n",
        b"x,y\n9007199254740992,a\n9007199254740993,b\n,a\n",
        b"x,y\n18446744073709551616,a\n18446744073709551617,b\n,a\n",
        b'x,y\n"line\none",true\n2025-01-01,false\n',
    ],
)
def test_embedded_parser_parity(tmp_path, content):
    module = imported_source(tmp_path, plan_for())
    path = tmp_path / "data.csv"
    path.write_bytes(content)
    pd.testing.assert_frame_equal(module.parse_csv_bytes(content), parse_source(path))
    assert (
        module.read_verified_bytes(
            path, "sha256:" + hashlib.sha256(content).hexdigest(), len(content)
        )
        == content
    )


@pytest.mark.parametrize("content", [b"", b"x,x\n1,2\n", b"x,y\n1\n", b"x\n", b"x\n\xff\n"])
def test_parser_rejects_malformed(content):
    with pytest.raises(ValueError):
        parse_csv_bytes(content)


def test_integrity_paths_and_finite_results(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes(b"x\n1\n")
    with pytest.raises(ValueError):
        read_verified_bytes(source, "sha256:wrong", source.stat().st_size)
    with pytest.raises(ValueError):
        read_verified_bytes(source, "sha256:wrong", 1)
    with pytest.raises(ValueError):
        runtime_paths(source, source, tmp_path / "model.joblib")
    with pytest.raises(ValueError):
        runtime_paths("relative.csv", tmp_path / "result.json", tmp_path / "model.joblib")
    with pytest.raises(ValueError):
        write_result(tmp_path / "result.json", {"metric": float("nan")})
    assert not (tmp_path / "result.json").exists()


@pytest.mark.parametrize("model", ["logistic_regression", "decision_tree", "random_forest"])
def test_constructor_and_complete_pipeline_library_compatibility(tmp_path, model):
    plan = plan_for(model, mixed=True)
    types = {
        c.__name__: c
        for c in [
            LogisticRegression,
            DecisionTreeClassifier,
            RandomForestClassifier,
            SimpleImputer,
            StandardScaler,
            MinMaxScaler,
            RobustScaler,
            OneHotEncoder,
        ]
    }

    def construct(spec):
        params = dict(spec.parameters)
        if params.get("missing_values") == "nan":
            params["missing_values"] = np.nan
        return types[spec.name](**params)

    branches = [
        (
            f"feature_{n}",
            Pipeline([(f"step_{i}", construct(op)) for i, op in enumerate(f.operations)]),
            [f.name],
        )
        for n, f in enumerate(plan.features)
    ]
    pipeline = Pipeline(
        [
            ("preprocessor", ColumnTransformer(branches, sparse_threshold=1.0)),
            ("model", construct(plan.model)),
        ]
    )
    _, _, frame = prepared(mixed=True)
    X = frame[[f.name for f in plan.features]].copy()
    X.loc[0, "age"] = np.nan
    # Isolated library test only. No generated main, production executor, or Run.
    pipeline.fit(X, frame.target)
    path = tmp_path / "complete.joblib"
    write_model(path, pipeline)
    restored = joblib.load(path)
    assert list(restored.named_steps) == ["preprocessor", "model"]
    assert len(restored.predict(X)) == len(X)
    assert (
        restored.named_steps["preprocessor"]
        .named_transformers_["feature_0"]
        .named_steps["step_0"]
        .statistics_[0]
        == 10
    )


@pytest.mark.parametrize("penalty,solver", [("l1", "liblinear"), ("l2", "lbfgs")])
def test_logistic_solver_compatibility(penalty, solver):
    model = LogisticRegression(
        penalty=penalty, solver=solver, l1_ratio=1.0 if penalty == "l1" else 0.0, random_state=42
    )
    model.fit([[0], [1], [2], [3]], [False, False, True, True])
    assert model.classes_.tolist() == [False, True]


@pytest.mark.parametrize(
    "counts,fraction,seed",
    [([10, 10], 0.2, 42), ([2, 6], 0.25, 0), ([2, 6], 0.25, 1), ([3, 3], 0.5, 42)],
)
def test_splitter_matches_count_validator(counts, fraction, seed):
    y = pd.Series(["a"] * counts[0] + ["b"] * counts[1])
    ir, _, _ = prepared()
    ir.split.test_size = fraction
    train_size, test_size = partition_sizes(len(y), ir.split)
    train, test = train_test_split(y, test_size=fraction, random_state=seed, stratify=y)
    assert (len(train), len(test)) == (train_size, test_size)
    assert (
        train.value_counts().reindex(["a", "b"], fill_value=0).tolist()
        == stratified_train_counts(counts, train_size, seed).tolist()
    )


def test_runtime_guards_and_metric_orientation():
    with pytest.raises(ValueError):
        validate_training_partition(pd.DataFrame({"x": [None, None]}), pd.Series([0, 1]))
    with pytest.raises(ValueError):
        validate_target(pd.Series(["a", "b", "c"]), scalar_record("a"), scalar_record("b"))

    class Scores:
        classes_ = np.array(["a", "z"])

        def predict_proba(self, X):
            return np.array([[0.9, 0.1], [0.1, 0.9]])

    metrics, matrix, reason = evaluate_predictions(
        Scores(), None, pd.Series(["a", "z"]), ["a", "z"], "a", "z"
    )
    assert metrics["roc_auc"] == 1 and metrics["f1"] == 1 and reason is None
    assert matrix == [[1, 0], [0, 1]]
    metrics, matrix, reason = evaluate_predictions(
        Scores(), None, pd.Series(["z", "z"]), ["z", "z"], "a", "z"
    )
    assert metrics["roc_auc"] is None and reason and metrics["precision"] == 0
    assert matrix == [[2, 0], [0, 0]]


def test_source_structure_and_no_hidden_workload():
    source = generate(plan_for(mixed=True))
    tree = ast.parse(source)
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    split = next(
        n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "train_test_split"
    )
    fit = next(n for n in calls if isinstance(n.func, ast.Attribute) and n.func.attr == "fit")
    assert split.lineno < fit.lineno
    assert ast.unparse(fit) == "model_pipeline.fit(X_train, y_train)"
    assert "write_model(model_path, model_pipeline)" in source
    assert "'dormant'" not in source
    assert "np.nan" in source
    assert "stratify=y" in source


def test_preview_has_no_execution_or_persistence_side_effects(client, settings, monkeypatch):
    project, _, path, state = experiment(client)
    state = save(client, path, state).json()

    def forbidden(*args, **kwargs):
        pytest.fail("Preview attempted execution")

    monkeypatch.setattr(Pipeline, "fit", forbidden)
    monkeypatch.setattr(LogisticRegression, "fit", forbidden)
    monkeypatch.setattr(joblib, "dump", forbidden)
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    files_before = sorted(str(p.relative_to(settings.home)) for p in settings.home.rglob("*"))
    response = client.get(f"/api/v1/projects/{project['id']}/code")
    assert response.status_code == 200
    code = response.json()
    assert code["ready"] and code["source"] and code["revision"] == state["revision"]
    assert code["source_sha256"] == "sha256:" + hashlib.sha256(code["source"].encode()).hexdigest()
    assert (
        sorted(str(p.relative_to(settings.home)) for p in settings.home.rglob("*")) == files_before
    )
    assert client.get(path).json() == state
    assert client.get(f"/api/v1/projects/{project['id']}/code").json() == code
    client.patch(f"/api/v1/projects/{project['id']}", json={"name": "Different display name"})
    assert client.get(f"/api/v1/projects/{project['id']}/code").json()["source"] == code["source"]


@pytest.mark.parametrize(
    "mutation", ["incomplete", "stale", "fingerprint", "missing", "corrupt", "target"]
)
def test_preview_refuses_invalid_context(client, settings, mutation):
    project, dataset, path, state = experiment(client)
    save(client, path, state)
    if mutation == "incomplete":
        state = client.get(path).json()
        state["ir"]["model"] = None
        save(client, path, state)
    elif mutation == "stale":
        upload(client, project, expected=dataset["id"])
    elif mutation == "fingerprint":
        next(settings.home.rglob("source.csv")).write_bytes(b"changed")
    elif mutation == "missing":
        next(settings.home.rglob("source.csv")).unlink()
    elif mutation == "corrupt":
        with client.app.state.session_factory() as session:
            p = session.scalar(select(Project).where(Project.id == project["id"]))
            p.working_pipeline = {"ir_version": "unsupported"}
            session.commit()
    else:
        configure(client, project, target_column="other")
    response = client.get(f"/api/v1/projects/{project['id']}/code")
    assert response.status_code == 200
    assert not response.json()["ready"] and response.json()["source"] is None
    assert response.json()["issues"]


def test_preview_empty_and_unknown_project(client):
    project = create(client)
    assert not client.get(f"/api/v1/projects/{project['id']}/code").json()["ready"]
    assert client.get("/api/v1/projects/missing/code").status_code == 404


def test_unknown_category_does_not_learn_test_vocabulary():
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=True, dtype="float64")
    encoder.fit(pd.DataFrame({"city": ["east", "west"]}))
    assert encoder.transform(pd.DataFrame({"city": ["new"]})).toarray().tolist() == [[0, 0]]
    assert encoder.categories_[0].tolist() == ["east", "west"]


def test_multiple_identical_feature_branches():
    ir, dataset, frame = prepared(mixed=True)
    ir.features["income"].operations = ir.features["age"].operations
    plan, _ = resolve(ir, dataset, "target", frame)
    source = generate(plan)
    assert source.count("StandardScaler(") == 2
    assert "'feature_000'" in source and "'feature_001'" in source
    assert [f.name for f in plan.features] == ["age", "income", "balance", "city"]


def test_decision_score_orientation_and_unavailable():
    class DecisionScores:
        classes_ = np.array(["a", "z"])

        def decision_function(self, X):
            return np.array([-2.0, 2.0])

    metrics, _, reason = evaluate_predictions(
        DecisionScores(), None, pd.Series(["a", "z"]), ["a", "z"], "a", "z"
    )
    assert metrics["roc_auc"] == 1 and reason is None

    class NoScores:
        classes_ = np.array(["a", "z"])

    metrics, _, reason = evaluate_predictions(
        NoScores(), None, pd.Series(["a", "z"]), ["a", "z"], "a", "z"
    )
    assert metrics["roc_auc"] is None and reason


def test_environment_and_parser_context_refusal():
    ir, dataset, frame = prepared()
    dataset.pandas_version = "unsupported"
    plan, issues = resolve(ir, dataset, "target", frame)
    assert plan is None and "parser_context" in {i.code for i in issues}
    with pytest.raises(ValueError):
        verify_environment({}, "unsupported")


def test_preview_library_failure_is_sanitized(client, monkeypatch):
    project, _, path, state = experiment(client)
    save(client, path, state)
    from mlstudio.services import code_preview

    def broken(plan):
        raise RuntimeError("sensitive row and absolute path")

    monkeypatch.setattr(code_preview, "generate", broken)
    response = client.get(f"/api/v1/projects/{project['id']}/code")
    assert response.status_code == 500 and "sensitive" not in response.text


def test_runtime_consumes_verified_buffer_after_source_replacement(tmp_path):
    source = tmp_path / "source.csv"
    original = b"x,y\n1,a\n2,b\n"
    source.write_bytes(original)
    data = read_verified_bytes(
        source, "sha256:" + hashlib.sha256(original).hexdigest(), len(original)
    )
    source.write_bytes(b"replacement")
    assert parse_csv_bytes(data).x.tolist() == [1, 2]


def test_api_target_representation_not_ready(client):
    project = create(client)
    content = "x,y\n" + "\n".join(f"{i},{0.1 if i % 2 else 0.6}" for i in range(20))
    upload(client, project, content.encode())
    configure(client, project, target_column="y")
    path = f"/api/v1/projects/{project['id']}/pipeline"
    state = client.get(path).json()
    state["ir"]["target"]["positive_class"] = {"value_type": "float", "value": 0.1}
    state["ir"].update(model={"type": "decision_tree"}, split={})
    response = save(client, path, state).json()
    assert not response["code_generation_ready"]
    preview = client.get(f"/api/v1/projects/{project['id']}/code").json()
    assert not preview["ready"] and preview["source"] is None
    assert "target_representation" in {i["code"] for i in preview["issues"]}


@pytest.mark.parametrize("dtype", ["Int64", "UInt64"])
def test_nullable_large_integer_identity_is_refused(dtype):
    ir, dataset, frame = prepared(labels=[2**53, 2**53 + 1])
    frame["target"] = frame.target.astype(dtype)
    assert not target_supported(frame.target)
    plan, issues = resolve(ir, dataset, "target", frame)
    assert plan is None and "target_representation" in {i.code for i in issues}
    # Even after missing-target exclusion the extension dtype remains, and sklearn
    # silently converts it to float64. It must not become a one-class classifier.
    assert frame.target.dropna().dtype == dtype


def test_nullable_large_categories_are_refused_without_changing_source():
    ir, dataset, frame = prepared()
    frame["age"] = pd.Series([2**53, 2**53 + 1] * 10, dtype="Int64")
    dataset.columns = describe_columns(frame)
    dataset.columns[0]["semantic_override"] = "categorical"
    original = frame.copy(deep=True)
    plan, issues = resolve(ir, dataset, "target", frame)
    assert plan is None and "feature_representation" in {i.code for i in issues}
    pd.testing.assert_frame_equal(original, frame)


@pytest.mark.parametrize(
    "labels", [["a", "z"], [0, 1], [1.0, 2.0], [False, True], [2**53, 2**53 + 1]]
)
@pytest.mark.parametrize(
    "model", [LogisticRegression, DecisionTreeClassifier, RandomForestClassifier]
)
def test_library_preserves_supported_labels_and_positive_orientation(labels, model):
    X = pd.DataFrame({"x": [0, 1] * 10})
    y = pd.Series(labels * 10)
    fitted = model(random_state=42).fit(X, y)
    assert [scalar_record(v) for v in fitted.classes_] == [scalar_record(v) for v in labels]
    metrics, matrix, reason = evaluate_predictions(
        fitted, X, y, fitted.predict(X), labels[0], labels[1]
    )
    assert metrics["roc_auc"] == 1 and metrics["f1"] == 1 and reason is None
    assert matrix == [[10, 0], [0, 10]]


def test_adversarial_target_and_label_are_only_literals():
    payload = plan_for().model_dump()
    name = "target'); __import__('os').system('bad') #"
    label = "quoted'\\\n\u65e5\u672c\u8a9e; __import__('os')"
    payload["target"]["column"] = name
    payload["target"]["positive_class"] = scalar_record(label)
    plan = EffectiveExecutionPlan.model_validate(payload)
    source = generate(plan)
    tree = ast.parse(source)
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
    }
    assert constants["TARGET"] == name and constants["POSITIVE_CLASS"] == label
    assert not any(isinstance(n, ast.Name) and n.id == "__import__" for n in ast.walk(tree))
    assert generate(plan).encode() == source.encode()
    compile(source, "generated_run.py", "exec")


def test_hash_order_independence_in_fresh_interpreters():
    # Render only, never invoke generated main. Hash randomization is selected at
    # interpreter startup, so changing os.environ in this process is insufficient.
    script = (
        "import hashlib; from test_codegen import generate, golden_plan; "
        "print(hashlib.sha256(generate(golden_plan('mixed')).encode()).hexdigest())"
    )
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=Path(__file__).parent,
            env={**os.environ, "PYTHONHASHSEED": seed},
            text=True,
        )
        for seed in ["1", "98765"]
    ]
    assert outputs[0] == outputs[1]


def test_parser_preserves_specific_safe_validation_errors():
    with pytest.raises(ValueError, match="column names must be unique"):
        parse_csv_bytes(b"x,x\n1,2\n")


def test_training_failure_message_is_safe_and_preserved(tmp_path):
    module = imported_source(tmp_path, plan_for())
    with pytest.raises(module.WorkloadValidationError, match="no observed values"):
        module.validate_training_partition(
            pd.DataFrame({"private-name": [None, None]}), pd.Series([0, 1])
        )
    source = generate(plan_for())
    assert "isinstance(error, WorkloadValidationError)" in source
