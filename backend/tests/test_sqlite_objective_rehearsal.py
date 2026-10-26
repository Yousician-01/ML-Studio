"""Prove the proposed rebuild's transaction/FK boundary on disposable v1 databases."""

import subprocess
import sys

import pytest
from released_v01 import (
    BACKEND,
    DATASETS,
    PROJECTS,
    RELEASED_HEAD,
    assert_preserved,
    build_released_workspace,
    migration_config,
    snapshot,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlite_objective_rehearsal import (
    REHEARSAL_HEAD,
    rehearsal_config,
    rehearse_objective_upgrade,
)

from alembic import command
from mlstudio.db.session import create_database_engine


@pytest.fixture
def released(settings):
    build_released_workspace(settings)
    return settings


FAULT_STATEMENTS = [
    "CREATE TABLE _alembic_tmp_projects",
    "INSERT INTO _alembic_tmp_projects",
    "DROP TABLE projects",
    "ALTER TABLE _alembic_tmp_projects RENAME TO projects",
    "UPDATE alembic_version",
    "PRAGMA integrity_check",
]


@pytest.mark.parametrize("statement", FAULT_STATEMENTS)
def test_rebuild_failure_rolls_back_rows_schema_and_revision_and_can_retry(
    released, tmp_path, statement
):
    before = snapshot(released)
    fired, restored = [], []

    def fail_after_sql(_connection, _cursor, sql, _parameters, _context, _many):
        if " ".join(sql.split()).startswith(statement) and not fired:
            fired.append(statement)
            raise RuntimeError("Injected migration failure")

    with pytest.raises(RuntimeError, match="Injected migration failure"):
        rehearse_objective_upgrade(
            released, tmp_path / "failure", after_statement=fail_after_sql, restored=restored
        )
    assert fired == [statement]  # Prove the intended destructive boundary was reached.
    assert restored == [{"foreign_keys": 1, "in_transaction": False}]
    after = snapshot(released)
    assert after == before
    assert after["heads"] == (RELEASED_HEAD,)
    rehearse_objective_upgrade(released, tmp_path / "retry")
    assert_preserved(before, snapshot(released), objective_changed=True)
    assert snapshot(released)["heads"] == (REHEARSAL_HEAD,)


def test_foreign_key_verification_aborts_bad_rebuild_before_commit(released, tmp_path):
    before = snapshot(released)
    restored = []

    def break_owner(connection, _cursor, sql, _parameters, _context, _many):
        if " ".join(sql.split()).startswith("ALTER TABLE _alembic_tmp_projects RENAME"):
            connection.execute(
                text("UPDATE projects SET active_dataset_id=:dataset WHERE id=:id"),
                {"dataset": DATASETS["other"], "id": PROJECTS["replaced"]},
            )

    with pytest.raises(ValueError, match="Foreign key violations after rebuild"):
        rehearse_objective_upgrade(
            released, tmp_path / "bad_owner", after_statement=break_owner, restored=restored
        )
    assert snapshot(released) == before
    assert restored == [{"foreign_keys": 1, "in_transaction": False}]


def test_preexisting_foreign_key_corruption_is_refused_without_repair(released, tmp_path):
    engine = create_database_engine(released)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            connection.execute(
                text("UPDATE projects SET active_dataset_id=:dataset WHERE id=:id"),
                {"dataset": DATASETS["other"], "id": PROJECTS["replaced"]},
            )
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
        before = snapshot(released)
        assert before["foreign_key_errors"]
        restored = []
        with pytest.raises(ValueError, match="Pre-existing foreign key violations"):
            rehearse_objective_upgrade(released, tmp_path / "corrupt", restored=restored)
        assert snapshot(released) == before
        assert restored == [{"foreign_keys": 1, "in_transaction": False}]
    finally:
        engine.dispose()


def test_disabling_foreign_keys_inside_transaction_does_not_permit_rebuild(released, tmp_path):
    before = snapshot(released)
    config = rehearsal_config(tmp_path / "wrong_pragma")
    engine = create_database_engine(released)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            config.attributes["connection"] = connection
            with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
                command.upgrade(config, "head")
            connection.rollback()
        assert snapshot(released) == before
    finally:
        engine.dispose()


def test_legacy_driver_transaction_without_explicit_begin_leaves_ddl_remnant(released, tmp_path):
    before = snapshot(released)
    config = rehearsal_config(tmp_path / "missing_begin")
    engine = create_database_engine(released)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            # SQLAlchemy's transaction alone does not start SQLite legacy-driver DDL.
            with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
                with connection.begin():
                    assert not connection.connection.driver_connection.in_transaction
                    command.upgrade(config, "head")
        after = snapshot(released)
        assert after["rows"] == before["rows"] and after["heads"] == before["heads"]
        assert set(after["tables"]) - set(before["tables"]) == {"_alembic_tmp_projects"}
    finally:
        engine.dispose()


def test_fresh_chain_and_repeated_rehearsal_preserve_schema_contract(settings, tmp_path):
    command.upgrade(migration_config(settings), RELEASED_HEAD)
    before = snapshot(settings)
    restored = []
    rehearse_objective_upgrade(settings, tmp_path / "fresh", restored=restored)
    after = snapshot(settings)
    assert_preserved(before, after, objective_changed=True)
    assert after["heads"] == (REHEARSAL_HEAD,)
    rehearse_objective_upgrade(settings, tmp_path / "again", restored=restored)
    assert snapshot(settings) == after
    assert restored == [{"foreign_keys": 1, "in_transaction": False}] * 2


def test_base_to_rehearsal_head_runs_actual_full_migration_chain(settings, tmp_path):
    rehearse_objective_upgrade(settings, tmp_path / "base")
    state = snapshot(settings)
    assert state["heads"] == (REHEARSAL_HEAD,)
    assert state["tables"] == ("alembic_version", "datasets", "projects", "runs")
    assert state["foreign_key_errors"] == []
    assert all(rows == [] for rows in state["rows"].values())


def test_process_death_after_parent_drop_recovers_original_database(released, tmp_path):
    before = snapshot(released)
    script = """import os, sys
sys.path.insert(0, sys.argv[3])
from pathlib import Path
from mlstudio.core.config import Settings
from sqlite_objective_rehearsal import rehearse_objective_upgrade

def die_after_drop(connection, cursor, sql, parameters, context, many):
    if " ".join(sql.split()).startswith("DROP TABLE projects"):
        os._exit(91)

settings = Settings(environment="test", home=Path(sys.argv[1]), database_url=None)
rehearse_objective_upgrade(settings, Path(sys.argv[2]), after_statement=die_after_drop)
"""
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            script,
            str(released.home),
            str(tmp_path / "crash"),
            str(BACKEND / "tests"),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=30,
    )
    assert child.returncode == 91, child.stderr.decode(errors="replace")
    # A new connection triggers SQLite journal recovery; no app repair is involved.
    assert snapshot(released) == before
    rehearse_objective_upgrade(released, tmp_path / "after_crash")
    assert_preserved(before, snapshot(released), objective_changed=True)
