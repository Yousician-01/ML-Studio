"""Disposable migration verification helpers.

Copies the five released migrations and appends a revision ONLY in pytest storage.
Foreign-key enforcement is disabled on one dedicated connection before an explicit
SQLite transaction, restored in finally, and checked before commit. This is the
The old naive environment remains only for negative boundary-characterization tests.
The upgrade wrapper now exercises the real production environment and revision.
"""

from pathlib import Path
from shutil import copyfile

from alembic.config import Config
from released_v01 import BACKEND, migration_config
from sqlalchemy import event

from alembic import command
from mlstudio.db.session import create_database_engine

REHEARSAL_HEAD = "0006_task_objectives"
ENVIRONMENT = """from alembic import context

connection = context.config.attributes["connection"]
context.configure(connection=connection, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
"""
REVISION = """import sqlalchemy as sa
from alembic import op

revision = "phase1_objective_rehearsal"
down_revision = "0005_tracking"
branch_labels = None
depends_on = None

def upgrade():
    table = sa.Table("projects", sa.MetaData(), autoload_with=op.get_bind())
    # text() parses :null inside the reflected JSON default as a bind parameter.
    # literal_column preserves the exact existing trusted schema SQL instead.
    for column in table.columns:
        if column.server_default is not None:
            column.server_default = sa.DefaultClause(
                sa.literal_column(str(column.server_default.arg))
            )
    with op.batch_alter_table("projects", recreate="always", copy_from=table) as batch:
        batch.drop_constraint("ck_project_objective", type_="check")
        batch.create_check_constraint(
            "ck_project_objective", "ml_objective IN ('binary_classification', 'regression')"
        )

def downgrade():
    raise NotImplementedError("Phase 1 does not rehearse lossy regression downgrades.")
"""


def rehearsal_config(directory):
    directory = Path(directory)
    versions = directory / "versions"
    versions.mkdir(parents=True)
    released = sorted((BACKEND / "alembic/versions").glob("000[1-5]_*.py"))
    assert len(released) == 5
    for source in released:
        copyfile(source, versions / source.name)
    (directory / "env.py").write_text(ENVIRONMENT, encoding="utf-8")
    (versions / "0006_rehearsal.py").write_text(REVISION, encoding="utf-8")
    config = Config()
    config.set_main_option("script_location", str(directory))
    return config


def rehearse_objective_upgrade(settings, directory, *, after_statement=None, restored=None):
    """Exercise the real production env/revision; directory is retained for callers."""
    if settings.environment != "test":
        raise ValueError("Migration verification is restricted to test settings.")
    config = migration_config(settings)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            if after_statement is not None:
                event.listen(connection, "after_cursor_execute", after_statement)
            config.attributes["connection"] = connection
            try:
                command.upgrade(config, "head")
            finally:
                if after_statement is not None:
                    event.remove(connection, "after_cursor_execute", after_statement)
                if restored is not None:
                    enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
                    connection.commit()
                    in_transaction = connection.connection.driver_connection.in_transaction
                    restored.append(
                        {
                            "foreign_keys": enabled,
                            "in_transaction": in_transaction,
                        }
                    )
    finally:
        engine.dispose()
