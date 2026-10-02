"""Read-only schema compatibility check; never migrates a user's database."""

from functools import lru_cache
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory


@lru_cache(maxsize=1)
def required_heads():
    return tuple(ScriptDirectory(str(Path(__file__).resolve().parents[3] / "alembic")).get_heads())


def migration_message(connection):
    required = required_heads()
    current = MigrationContext.configure(connection).get_current_heads()
    if set(current) != set(required):
        return (
            f"Database migration required. Current revision: {', '.join(current) or 'none'}. "
            f"Required revision: {', '.join(required)}. "
            "From the backend directory run: python -m alembic upgrade head. "
            "If the database is from a newer app version, use that version instead."
        )
    return None
