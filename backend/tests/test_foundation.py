from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from alembic import command
from mlstudio.core.config import Settings
from mlstudio.db.session import create_database_engine, get_session
from mlstudio.main import create_app


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ml-studio-api", "database": "ready"}


def test_database_readiness(settings: Settings):
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert Path(str(engine.url.database)).is_file()
    finally:
        engine.dispose()


def test_workspace_override(tmp_path: Path, settings: Settings):
    assert settings.home == tmp_path / "workspace"
    assert settings.resolved_database_url.database == str(settings.home / "mlstudio.db")
    assert not settings.home.exists()  # Resolving settings has no filesystem side effects.
    create_app(settings)
    assert not settings.home.exists()


def test_database_failure_is_sanitized(client: TestClient):
    class BrokenSession:
        def execute(self, statement):
            raise OperationalError("private internal path", {}, Exception("secret"))

    client.app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_cors_explicit_origins(client: TestClient):
    allowed = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in allowed.headers
    denied = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_rejects_unsafe_or_unsupported_configuration():
    with pytest.raises(ValidationError):
        Settings(cors_origins=["*"])
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://localhost/mlstudio")


def test_migrations_on_fresh_database(settings: Settings):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.attributes["settings"] = settings
    command.upgrade(config, "head")
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision == ScriptDirectory.from_config(config).get_current_head()
            assert inspect(connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")  # Re-running is safe.
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    finally:
        engine.dispose()
