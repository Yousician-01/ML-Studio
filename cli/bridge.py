"""CLI-only adapter to existing backend configuration and Alembic, not a server.

No API, execution, persistence-model, or ML behavior is implemented here.
"""

import fnmatch
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from mlstudio.core.config import Settings


class BridgeError(Exception):
    """Only fixed CLI-authored messages may cross the diagnostics boundary."""


def configuration():
    settings = Settings()
    config = Config(str(Path(__file__).resolve().parents[1] / "backend/alembic.ini"))
    config.attributes["settings"] = settings
    return settings, config


def schema_state(settings, config):
    database = Path(settings.resolved_database_url.database)
    current = ()
    if database.exists():
        # Read-only SQLite URI: diagnostics must not initialize or migrate a DB.
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone():
                current = tuple(
                    row[0] for row in connection.execute("SELECT version_num FROM alembic_version")
                )
    heads = tuple(ScriptDirectory.from_config(config).get_heads())
    return {"current": current, "required": heads, "ready": set(current) == set(heads)}


def backup(settings):
    """Offline full-workspace copy plus SQLite backup API (including external DB).

    CLI checks its locks and default ports; user must stop non-CLI writers too.
    Links are refused instead of traversing outside the selected workspace.
    """
    home = settings.home
    database = Path(settings.resolved_database_url.database)
    if not home.exists() and not database.exists():
        return None
    destination = home.parent / (home.name + " backups") / str(uuid4())
    destination.mkdir(parents=True, mode=0o700)
    database_files = {
        database,
        *(Path(str(database) + suffix) for suffix in ("-wal", "-shm", "-journal")),
    }

    def excluded(directory, names):
        patterns = (
            "*.db",
            "*.db-*",
            "*.sqlite",
            "*.sqlite-*",
            "*.sqlite3",
            "*.sqlite3-*",
            ".mls-runtime.lock",
        )
        return [
            name
            for name in names
            if Path(directory) / name in database_files
            or any(fnmatch.fnmatch(name, pattern) for pattern in patterns)
        ]

    try:
        if home.exists():
            for path in home.rglob("*"):
                if path.is_symlink() or path.is_junction():
                    raise BridgeError("Workspace links require an explicit offline backup")
            shutil.copytree(
                home,
                destination / "workspace",
                ignore=excluded,
            )
            for path in home.rglob("*"):
                if path.is_file() and path.suffix in {".db", ".sqlite", ".sqlite3"}:
                    backup_sqlite(path, destination / "workspace" / path.relative_to(home))
            # Custom database URLs need not have a conventional SQLite extension.
            if database.exists() and database.is_relative_to(home):
                backup_sqlite(database, destination / "workspace" / database.relative_to(home))
        if database.exists() and not database.is_relative_to(home):
            backup_sqlite(database, destination / "external-database.sqlite")
        (destination / "recovery.json").write_text(
            json.dumps(
                {
                    "home": str(home),
                    "database": str(database),
                    "external_database": not database.is_relative_to(home),
                    "instructions": (
                        "Stop all ML Studio processes. Restore workspace and "
                        "external-database.sqlite "
                        "(if present) together to their original paths using the matching revision."
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except BaseException:
        # Retain partial copy for diagnostics, but never proceed to migrations.
        raise BridgeError("Backup failed; migration was not started") from None
    return str(destination)


def backup_sqlite(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src,
        closing(sqlite3.connect(destination)) as dst,
    ):
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise BridgeError("Backup integrity check failed")


def main():
    settings, config = configuration()
    action = sys.argv[1]
    if action == "settings":
        if "http://127.0.0.1:3000" not in settings.cors_origins:
            raise BridgeError("MLSTUDIO_CORS_ORIGINS must include http://127.0.0.1:3000")
        result = {
            "home": str(settings.home),
            "database": str(settings.resolved_database_url.database),
            "api_prefix": settings.api_prefix,
            "code_execution_enabled": settings.code_execution_enabled,
        }
    elif action == "doctor":
        result = schema_state(settings, config)
    elif action == "migrate":
        state = schema_state(settings, config)
        location = None
        if not state["ready"]:
            # An unknown/newer revision is rejected by Alembic without stamping/reset.
            location = backup(settings)
            if location:
                print(f"Pre-upgrade backup retained at: {location}", file=sys.stderr)
            command.upgrade(config, "head")
        state = schema_state(settings, config)
        if not state["ready"]:
            raise BridgeError("Database is not at the required revision")
        result = {"ready": True, "backup": location}
    else:
        raise BridgeError("Unknown CLI bridge action")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except BridgeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # Never print Pydantic inputs, environment secrets, raw rows or SQL values.
        print(
            "CLI backend operation failed. Check configuration, permissions, free disk space "
            "and migration compatibility. Existing workspace was not reset.",
            file=sys.stderr,
        )
        sys.exit(1)
