from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mlstudio.core.config import Settings
from mlstudio.main import create_app


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path: Path):
    import os

    for name in os.environ:
        if name.startswith("MLSTUDIO_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("MLSTUDIO_HOME", str(tmp_path / "workspace"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test")


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as client:
        yield client
