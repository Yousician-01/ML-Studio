"""Durable local execution attempts and non-reusable Project sequence allocation."""

import sqlalchemy as sa

from alembic import op

revision = "0004_runs"
down_revision = "0003_working_pipeline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects", sa.Column("next_run_sequence", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(71), nullable=False),
        sa.Column("plan_sha256", sa.String(71), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(32)),
        sa.Column("finished_at", sa.String(32)),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("failure", sa.JSON()),
        sa.UniqueConstraint("project_id", "sequence", name="uq_run_sequence"),
        sa.UniqueConstraint("project_id", "request_id", name="uq_run_request"),
        sa.ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["datasets.project_id", "datasets.id"],
            name="fk_run_dataset_owner",
        ),
        sa.CheckConstraint("sequence > 0 AND revision > 0", name="ck_run_sequence_revision"),
        sa.CheckConstraint(
            "state IN ('CREATED','RUNNING','SUCCEEDED','FAILED')", name="ck_run_state"
        ),
        sa.CheckConstraint(
            "(state IN ('CREATED','RUNNING') AND finished_at IS NULL) OR "
            "(state IN ('SUCCEEDED','FAILED') AND finished_at IS NOT NULL)",
            name="ck_run_terminal_time",
        ),
        sa.CheckConstraint("state != 'CREATED' OR started_at IS NULL", name="ck_run_created_time"),
        sa.CheckConstraint(
            "state NOT IN ('RUNNING','SUCCEEDED') OR started_at IS NOT NULL",
            name="ck_run_started_time",
        ),
    )
    op.create_index("ix_runs_project_id", "runs", ["project_id"])


def downgrade():
    op.drop_table("runs")
    op.drop_column("projects", "next_run_sequence")
