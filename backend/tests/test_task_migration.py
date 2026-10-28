"""Production task migration and application readiness, on disposable databases."""

import pytest
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from fastapi.testclient import TestClient
from released_v01 import PROJECTS, build_released_workspace, migration_config, snapshot
from sqlalchemy import event, text

from alembic import command
from mlstudio.db.session import create_database_engine
from mlstudio.main import create_app


def test_released_upgrade_widens_objective_and_restores_normal_foreign_keys(settings):
    build_released_workspace(settings)
    config = migration_config(settings)
    command.upgrade(config, "head")
    assert snapshot(settings)["heads"] == (ScriptDirectory.from_config(config).get_current_head(),)
    engine = create_database_engine(settings)
    try:
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            connection.execute(
                text("UPDATE projects SET ml_objective='regression' WHERE id=:id"),
                {"id": PROJECTS["empty"]},
            )
        before_downgrade = snapshot(settings)
        with pytest.raises(CommandError, match="Downgrade.*refused"):
            command.downgrade(config, "0005_tracking")
        assert snapshot(settings) == before_downgrade
    finally:
        engine.dispose()


def test_application_requires_new_head_then_accepts_upgrade(settings):
    build_released_workspace(settings)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/projects")
        assert response.status_code == 503
        assert (
            ScriptDirectory.from_config(migration_config(settings)).get_current_head()
            in response.json()["detail"]
        )
    command.upgrade(migration_config(settings), "head")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/projects").status_code == 200


@pytest.mark.parametrize("destination", ["+1", "0006_task_objectives", "head"])
def test_revision_traversal_selects_rebuild_for_actual_pending_upgrade(settings, destination):
    build_released_workspace(settings)
    command.upgrade(migration_config(settings), destination)
    expected = (
        ScriptDirectory.from_config(migration_config(settings)).get_current_head()
        if destination == "head"
        else "0006_task_objectives"
    )
    assert snapshot(settings)["heads"] == (expected,)


def test_special_handling_is_absent_for_old_and_already_applied_upgrades(settings):
    engine = create_database_engine(settings)
    statements = []
    try:
        with engine.connect() as connection:
            event.listen(
                connection,
                "after_cursor_execute",
                lambda _c, _r, sql, _p, _x, _m: statements.append(sql),
            )
            config = migration_config(settings)
            config.attributes["connection"] = connection
            command.upgrade(config, "0005_tracking")
            assert "PRAGMA foreign_keys=OFF" not in statements
            assert "BEGIN IMMEDIATE" not in statements
            statements.clear()
            command.upgrade(config, "head")
            assert "PRAGMA foreign_keys=OFF" in statements
            assert "BEGIN IMMEDIATE" in statements
            statements.clear()
            command.upgrade(config, "head")
            assert "PRAGMA foreign_keys=OFF" not in statements
            assert "BEGIN IMMEDIATE" not in statements
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    finally:
        engine.dispose()


def test_released_migration_chain_retains_its_existing_downgrade_path(settings):
    config = migration_config(settings)
    command.upgrade(config, "0005_tracking")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert snapshot(settings)["heads"] == (ScriptDirectory.from_config(config).get_current_head(),)
