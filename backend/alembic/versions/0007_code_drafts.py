"""Persistent Code Mode sessions and independent immutable code snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "0007_code_drafts"
down_revision = "0006_task_objectives"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "code_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin_revision", sa.Integer(), nullable=False),
        sa.Column("origin_ir", sa.JSON(), nullable=False),
        sa.Column("baseline_source", sa.Text(), nullable=False),
        sa.Column("baseline_sha256", sa.String(71), nullable=False),
        sa.Column("plan_sha256", sa.String(71), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','archived','discarded')", name="ck_code_draft_status"
        ),
        sa.CheckConstraint("revision > 0 AND origin_revision > 0", name="ck_code_draft_revision"),
    )
    op.create_index("ix_code_drafts_project_id", "code_drafts", ["project_id"])
    op.create_index(
        "uq_code_draft_active_project",
        "code_drafts",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "code_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "draft_id",
            sa.String(36),
            sa.ForeignKey("code_drafts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(71), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
    )
    op.create_index("ix_code_snapshots_draft_id", "code_snapshots", ["draft_id"])


def downgrade():
    # Refuse implicit loss of manual work, consistent with the objective migration.
    from alembic.util import CommandError

    raise CommandError(
        "Downgrade from Code Mode is refused. Restore a consistent pre-upgrade backup."
    )
