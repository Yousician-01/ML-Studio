"""Phase 1 metadata. Source rows are deliberately absent from these tables."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from mlstudio.db.base import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "active_dataset_id"],
            ["datasets.project_id", "datasets.id"],
            name="fk_project_active_dataset_owner",
            use_alter=True,  # Break metadata sorting cycles; SQLite still emits this inline.
        ),
        CheckConstraint("ml_objective = 'binary_classification'", name="ck_project_objective"),
        CheckConstraint(
            "active_dataset_id IS NOT NULL OR target_column IS NULL",
            name="ck_target_requires_dataset",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None]
    problem_statement: Mapped[str]
    success_context: Mapped[str | None]
    ml_objective: Mapped[str] = mapped_column(String(32), default="binary_classification")
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    active_dataset_id: Mapped[str | None] = mapped_column(String(36))
    target_column: Mapped[str | None]
    # Target transition context only; not a feature editor or a second Pipeline IR.
    # Later IR initialization must keep these former targets excluded.
    former_targets: Mapped[list[str]] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": revision}


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_dataset_owner_id"),
        CheckConstraint("format = 'csv'", name="ck_dataset_format"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    original_filename: Mapped[str]
    format: Mapped[str] = mapped_column(String(8), default="csv")
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    fingerprint: Mapped[str] = mapped_column(String(71))
    source_relative_path: Mapped[str]
    size_bytes: Mapped[int]
    row_count: Mapped[int]
    column_count: Mapped[int]
    missing_cells: Mapped[int]
    duplicate_rows: Mapped[int]
    parsing_version: Mapped[str] = mapped_column(String(32), default="csv-utf8-v1")
    pandas_version: Mapped[str] = mapped_column(String(32))
    columns: Mapped[list[dict]] = mapped_column(JSON)
