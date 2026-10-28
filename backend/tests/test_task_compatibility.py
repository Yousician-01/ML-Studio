"""Released v1 evidence must survive current/future schema upgrades byte-for-byte."""

import hashlib
import json

import pytest
from alembic.script import ScriptDirectory
from released_v01 import (
    BACKEND,
    DATASETS,
    EMPTY_IR,
    GOLDEN_HASHES,
    PROJECTS,
    RELEASED_HEAD,
    RUNS,
    assert_preserved,
    build_released_workspace,
    historical_python,
    migration_config,
    sha,
    snapshot,
)
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlite_objective_rehearsal import REHEARSAL_HEAD, rehearse_objective_upgrade
from test_codegen import golden_plan

from alembic import command
from mlstudio.codegen.render import generate
from mlstudio.codegen.schemas import EffectiveExecutionPlan
from mlstudio.db.session import create_database_engine
from mlstudio.execution.results import validate_result
from mlstudio.execution.service import historical_source, response
from mlstudio.models import Dataset, Project, Run
from mlstudio.pipeline_schemas import PipelineIR


@pytest.fixture
def released(settings):
    build_released_workspace(settings)
    return settings


@pytest.mark.parametrize("case", GOLDEN_HASHES)
def test_released_binary_goldens_keep_exact_bytes(case):
    expected = GOLDEN_HASHES[case]
    assert (
        hashlib.sha256((BACKEND / f"tests/golden/{case}.py.txt").read_bytes()).hexdigest()
        == expected
    )
    assert hashlib.sha256(generate(golden_plan(case)).encode()).hexdigest() == expected


def test_fixture_covers_released_states_without_current_defaults(released):
    engine = create_database_engine(released)
    try:
        with Session(engine) as session:
            projects = {p.id: p for p in session.scalars(select(Project))}
            assert {p.id: p.revision for p in projects.values()} == {
                PROJECTS["empty"]: 3,
                PROJECTS["incomplete"]: 9,
                PROJECTS["replaced"]: 17,
                PROJECTS["other"]: 4,
            }
            assert projects[PROJECTS["empty"]].active_dataset_id is None
            incomplete = projects[PROJECTS["incomplete"]]
            assert incomplete.target_column == "target"
            assert incomplete.working_pipeline["target"]["positive_class"] is None
            assert incomplete.working_pipeline["model"] is None
            assert incomplete.working_pipeline["split"] is None
            stale = projects[PROJECTS["replaced"]]
            assert stale.active_dataset_id == DATASETS["replacement"]
            assert stale.target_column is None and stale.next_run_sequence == 3
            assert stale.working_pipeline["dataset"]["dataset_id"] == DATASETS["historical"]
            assert session.get(Run, RUNS["success"]).state == "SUCCEEDED"
            failed = session.get(Run, RUNS["failed"])
            assert failed.state == "FAILED" and failed.result is None
            assert failed.failure["stage"] == "training"
            assert session.get(Dataset, DATASETS["historical"]).project_id == stale.id
        state = snapshot(released)
        assert state["heads"] == (RELEASED_HEAD,)
        assert state["foreign_key_errors"] == []
        assert len(state["rows"]["datasets"]) == 4
        assert len(state["rows"]["runs"]) == 2
    finally:
        engine.dispose()


def assert_history_readable(settings):
    engine = create_database_engine(settings)
    try:
        with Session(engine) as session:
            for run in session.scalars(select(Run)):
                detail = response(run, settings.home, detail=True).model_dump(mode="json")
                assert detail["state"] == run.state
                assert detail["result"] == run.result
                assert detail["failure"] == run.failure
                assert detail["mlflow_run_id"] == ("a" if run.state == "SUCCEEDED" else "b") * 32
                assert detail["tracking_status"] == "SYNCHRONIZED"
                assert detail["pipeline_ir"] == json.loads(
                    (settings.home / run.artifacts["pipeline_ir.json"]["path"]).read_bytes()
                )
                PipelineIR.model_validate(detail["pipeline_ir"])
                plan = EffectiveExecutionPlan.model_validate(detail["execution_plan"])
                source = historical_source(run, settings.home).encode()
                dataset = session.get(Dataset, run.dataset_id)
                dataset_values = {
                    c.name: getattr(dataset, c.name) for c in Dataset.__table__.columns
                }
                assert source == historical_python(dataset_values)
                assert generate(plan).encode() == source
                assert sha(source) == run.source_sha256
                assert all(ref["integrity"] == "verified" for ref in detail["artifacts"].values())
                if run.result is not None:
                    path = settings.home / run.artifacts["result.json"]["path"]
                    assert (
                        validate_result(
                            path, 1024 * 1024, detail["execution_plan"], run.manifest["population"]
                        )
                        == run.result
                    )
    finally:
        engine.dispose()


def test_released_history_is_read_only_and_current_head_upgrade_preserves_everything(released):
    before = snapshot(released)
    assert_history_readable(released)
    config = migration_config(released)
    command.upgrade(config, "head")
    assert_history_readable(released)
    after = snapshot(released)
    assert after["heads"] == tuple(ScriptDirectory.from_config(config).get_heads())
    assert_preserved(
        before,
        after,
        objective_changed=True,
        added_tables=("code_drafts", "code_runs", "code_snapshots"),
    )


@pytest.mark.parametrize("damage", ["source_missing", "source_changed", "code_changed"])
@pytest.mark.parametrize("rebuild", [False, True])
def test_upgrade_preserves_unavailable_evidence_without_repair(released, damage, rebuild, tmp_path):
    engine = create_database_engine(released)
    try:
        with Session(engine) as session:
            run = session.get(Run, RUNS["success"])
            ref = (
                run.artifacts["generated_run.py"]
                if damage == "code_changed"
                else run.manifest["dataset"]
            )
            path = released.home / ref["path"]
            if damage == "source_missing":
                path.unlink()
            else:
                path.write_bytes(path.read_bytes() + b"\n# changed in disposable fixture\n")
            original_result = run.result
        before = snapshot(released)
        if rebuild:
            rehearse_objective_upgrade(released, tmp_path / "rehearsal")
        else:
            command.upgrade(migration_config(released), "head")
        after = snapshot(released)
        expected_heads = (
            (REHEARSAL_HEAD,)
            if rebuild
            else tuple(ScriptDirectory.from_config(migration_config(released)).get_heads())
        )
        assert after["heads"] == expected_heads
        assert_preserved(
            before,
            after,
            objective_changed=True,
            added_tables=() if rebuild else ("code_drafts", "code_runs", "code_snapshots"),
        )
        with Session(engine) as session:
            detail = response(session.get(Run, RUNS["success"]), released.home, detail=True)
            assert detail.state == "SUCCEEDED" and detail.result == original_result
            key = "generated_run.py" if damage == "code_changed" else "dataset_source"
            assert detail.artifacts[key]["integrity"] == (
                "missing" if damage == "source_missing" else "unavailable_or_corrupt"
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE projects SET active_dataset_id=:dataset WHERE id=:other",
        "UPDATE datasets SET project_id=:other WHERE id=:dataset",
        "UPDATE runs SET project_id=:other WHERE id=:run",
    ],
)
@pytest.mark.parametrize("rebuild", [False, True])
def test_released_owner_constraints_reject_cross_project_references(
    released, statement, rebuild, tmp_path
):
    if rebuild:
        rehearse_objective_upgrade(released, tmp_path / "rehearsal")
    engine = create_database_engine(released)
    try:
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text(statement),
                    {
                        "dataset": DATASETS["historical"],
                        "other": PROJECTS["other"],
                        "run": RUNS["success"],
                    },
                )
    finally:
        engine.dispose()


def test_rehearsal_widens_only_disposable_objective_constraint(released, tmp_path):
    before = snapshot(released)
    rehearse_objective_upgrade(released, tmp_path / "rehearsal")
    after = snapshot(released)
    assert_preserved(before, after, objective_changed=True)
    assert_history_readable(released)
    engine = create_database_engine(released)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE projects SET ml_objective='regression' WHERE id=:id"),
                {"id": PROJECTS["empty"]},
            )
            assert (
                connection.execute(
                    text("SELECT ml_objective FROM projects WHERE id=:id"),
                    {"id": PROJECTS["empty"]},
                ).scalar_one()
                == "regression"
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text("UPDATE projects SET ml_objective='clustering' WHERE id=:id"),
                    {"id": PROJECTS["empty"]},
                )
    finally:
        engine.dispose()


def test_rehearsal_preserves_usable_json_server_default(released, tmp_path):
    rehearse_objective_upgrade(released, tmp_path / "rehearsal")
    engine = create_database_engine(released)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO projects (id,name,problem_statement,ml_objective,created_at,"
                "updated_at,revision) VALUES ('new','New','Predict','binary_classification',"
                "'now','now',1)"
            )
            stored = connection.exec_driver_sql(
                "SELECT working_pipeline,next_run_sequence FROM projects WHERE id='new'"
            ).one()
            assert json.loads(stored.working_pipeline) == EMPTY_IR
            assert stored.next_run_sequence == 1
    finally:
        engine.dispose()
