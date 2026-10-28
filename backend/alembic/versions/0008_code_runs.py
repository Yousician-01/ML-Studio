"""Independent managed Python execution records, without changing visual Runs."""

import sqlalchemy as sa
from alembic.util import CommandError

from alembic import op

revision = "0008_code_runs"
down_revision = "0007_code_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "code_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "draft_id",
            sa.String(36),
            sa.ForeignKey("code_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.String(36),
            sa.ForeignKey("code_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("submitted_revision", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(71), nullable=False),
        sa.Column("entrypoint", sa.String(), nullable=False),
        sa.Column("artifact_directory", sa.String(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(32)),
        sa.Column("finished_at", sa.String(32)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("error", sa.String()),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("logs", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "request_id", name="uq_code_run_request"),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="ck_code_run_status",
        ),
    )
    op.create_index("ix_code_runs_project_id", "code_runs", ["project_id"])
    op.create_index(
        "uq_code_run_active_project",
        "code_runs",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('PENDING','RUNNING')"),
    )


def downgrade():
    raise CommandError("Downgrade from Code Runs is refused. Restore a consistent backup.")
