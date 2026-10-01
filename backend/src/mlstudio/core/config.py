from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from platformdirs import user_data_path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MLSTUDIO_", env_file=".env", extra="ignore", populate_by_name=True
    )

    app_name: str = "ML Studio"
    environment: Literal["development", "production", "test"] = "development"
    api_prefix: str = "/api/v1"
    home: Path = Field(default_factory=lambda: user_data_path("ML Studio", appauthor=False))
    database_url: str | None = None
    max_csv_upload_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("home")
    @classmethod
    def resolve_home(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("api_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not value.startswith("/") or value.endswith("/"):
            raise ValueError("API prefix must start with / and have no trailing slash")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
        return values

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        if value is not None:
            url = make_url(value)
            if url.drivername not in {"sqlite", "sqlite+pysqlite"}:
                raise ValueError("Phase 0 supports synchronous SQLite only")
            if not url.database or not Path(url.database).is_absolute() or url.query:
                raise ValueError(
                    "Database URL must name an absolute SQLite file without URL options"
                )
        return value

    @property
    def resolved_database_url(self) -> URL:
        if self.database_url:
            return make_url(self.database_url)
        return URL.create("sqlite+pysqlite", database=str(self.home / "mlstudio.db"))
