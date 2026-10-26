"""Offline SQLite ownership-safe rebuild boundary, not application schema creation."""

from alembic.script.revision import RangeNotAncestorError
from alembic.util import CommandError

OBJECTIVE_REVISION = "0006_task_objectives"


def objective_rebuild_pending(script, destination, current_heads):
    """Only a traversal entering the new revision needs the special connection."""
    try:
        return any(
            r.revision == OBJECTIVE_REVISION
            for r in script.iterate_revisions(destination, current_heads or "base")
        )
    except (CommandError, RangeNotAncestorError):
        # A downgrade is not an upgrade traversal. Leave it (and invalid revision
        # requests) to Alembic's ordinary validation, without changing FK behavior.
        return False


def checked_objective_upgrade(connection, migrate):
    if connection.connection.driver_connection.in_transaction:
        raise RuntimeError("Objective rebuild requires a dedicated idle migration connection.")
    connection.commit()  # End any SQLAlchemy-only transaction from revision discovery.
    try:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        connection.commit()
        if enabled != 0:
            raise RuntimeError("Cannot establish the SQLite migration boundary.")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        if not connection.connection.driver_connection.in_transaction:
            raise RuntimeError("SQLite migration transaction did not start.")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Pre-existing foreign key violations; upgrade refused.")
        migrate()
        if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key violations after rebuild; upgrade rolled back.")
        if connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() != ["ok"]:
            raise ValueError("SQLite integrity validation failed; upgrade rolled back.")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        connection.commit()
        if enabled != 1:
            raise RuntimeError("SQLite foreign-key enforcement could not be restored.")
