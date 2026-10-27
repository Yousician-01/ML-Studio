"""Phase 1 metadata. Source rows are deliberately absent from these tables."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mlstudio.db.base import Base
from mlstudio.services.pipeline_state import empty_pipeline


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
        CheckConstraint(
            "ml_objective IN ('binary_classification', 'regression')", name="ck_project_objective"
        ),
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
    working_pipeline: Mapped[dict] = mapped_column(
        JSON,
        default=lambda context: empty_pipeline(context.get_current_parameters()["ml_objective"]),
    )
    revision: Mapped[int] = mapped_column(default=1)
    next_run_sequence: Mapped[int] = mapped_column(default=1, server_default="1")
    __mapper_args__ = {"version_id_col": revision}


@event.listens_for(Project, "before_update")
def protect_project_task(_mapper, _connection, project):
    if inspect(project).attrs.ml_objective.history.has_changes():
        raise ValueError("Project objective is immutable after creation.")


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


class CodeDraft(Base):
    """Editable text bound to preserved visual intent, never an execution."""

    __tablename__ = "code_drafts"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived','discarded')", name="ck_code_draft_status"),
        CheckConstraint("revision > 0 AND origin_revision > 0", name="ck_code_draft_revision"),
        Index(
            "uq_code_draft_active_project",
            "project_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    origin_revision: Mapped[int]
    origin_ir: Mapped[dict] = mapped_column(JSON)
    baseline_source: Mapped[str] = mapped_column(Text)
    baseline_sha256: Mapped[str] = mapped_column(String(71))
    plan_sha256: Mapped[str] = mapped_column(String(71))
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    revision: Mapped[int] = mapped_column(default=1)
    __mapper_args__ = {"version_id_col": revision}


class CodeSnapshot(Base):
    __tablename__ = "code_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("code_drafts.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(71))
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)


@event.listens_for(CodeDraft, "before_update")
def protect_code_origin(_mapper, _connection, draft):
    state = inspect(draft)
    changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
    old = state.attrs.status.history.deleted
    if changed - {"source", "status", "updated_at", "revision"} or (
        (old[0] if old else draft.status) != "active"
    ):
        raise ValueError("Code origin and ended sessions are immutable.")


@event.listens_for(CodeSnapshot, "before_update")
def protect_code_snapshot(_mapper, _connection, _snapshot):
    raise ValueError("Code snapshots are immutable and are not Runs.")


class Run(Base):
    """Frozen attempt inputs; only lifecycle/output fields change while active."""

    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_run_sequence"),
        UniqueConstraint("project_id", "request_id", name="uq_run_request"),
        ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["datasets.project_id", "datasets.id"],
            name="fk_run_dataset_owner",
        ),
        CheckConstraint("sequence > 0 AND revision > 0", name="ck_run_sequence_revision"),
        CheckConstraint("state IN ('CREATED','RUNNING','SUCCEEDED','FAILED')", name="ck_run_state"),
        CheckConstraint(
            "(state IN ('CREATED','RUNNING') AND finished_at IS NULL) OR "
            "(state IN ('SUCCEEDED','FAILED') AND finished_at IS NOT NULL)",
            name="ck_run_terminal_time",
        ),
        CheckConstraint("state != 'CREATED' OR started_at IS NULL", name="ck_run_created_time"),
        CheckConstraint(
            "state NOT IN ('RUNNING','SUCCEEDED') OR started_at IS NOT NULL",
            name="ck_run_started_time",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int]
    request_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int]
    source_sha256: Mapped[str] = mapped_column(String(71))
    plan_sha256: Mapped[str] = mapped_column(String(71))
    state: Mapped[str] = mapped_column(String(16), default="CREATED")
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    manifest: Mapped[dict] = mapped_column(JSON)
    artifacts: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    failure: Mapped[dict | None] = mapped_column(JSON)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    tracking_status: Mapped[str] = mapped_column(
        String(24), default="NOT_ATTEMPTED", server_default="NOT_ATTEMPTED"
    )
    tracking_error: Mapped[str | None]
    tracking_updated_at: Mapped[str | None] = mapped_column(String(32))


@event.listens_for(Run, "before_update")
def protect_run_history(_mapper, _connection, run):
    """Application ORM writes cannot rewrite frozen inputs or terminal facts."""
    state = inspect(run)
    changes = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    tracking = {"mlflow_run_id", "tracking_status", "tracking_error", "tracking_updated_at"}
    if changes <= tracking:
        previous_id = state.attrs.mlflow_run_id.history.deleted
        if previous_id and previous_id[0] is not None and previous_id[0] != run.mlflow_run_id:
            raise ValueError("Established MLflow identity cannot be replaced.")
        return
    mutable = {"state", "started_at", "finished_at", "artifacts", "result", "failure"}
    previous = state.attrs.state.history.deleted
    old_state = previous[0] if previous else run.state
    if changes - mutable or old_state in ("SUCCEEDED", "FAILED"):
        raise ValueError("Historical Run facts are immutable.")
    old_artifacts = state.attrs.artifacts.history.deleted
    if old_artifacts and any(
        run.artifacts.get(key) != ref for key, ref in old_artifacts[0].items()
    ):
        raise ValueError("Frozen artifact references are immutable.")
    allowed = {
        "CREATED": {"CREATED", "RUNNING", "FAILED"},
        "RUNNING": {"RUNNING", "SUCCEEDED", "FAILED"},
    }
    if run.state not in allowed[old_state]:
        raise ValueError("Invalid Run lifecycle transition.")
