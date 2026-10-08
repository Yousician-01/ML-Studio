"""Separately repairable MLflow association; immutable execution facts stay unchanged."""

import sqlalchemy as sa

from alembic import op

revision = "0005_tracking"
down_revision = "0004_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("runs", sa.Column("mlflow_run_id", sa.String(64), nullable=True))
    op.add_column(
        "runs",
        sa.Column("tracking_status", sa.String(24), nullable=False, server_default="NOT_ATTEMPTED"),
    )
    op.add_column("runs", sa.Column("tracking_error", sa.String(), nullable=True))
    op.add_column("runs", sa.Column("tracking_updated_at", sa.String(32), nullable=True))


def downgrade():
    for name in ("tracking_updated_at", "tracking_error", "tracking_status", "mlflow_run_id"):
        op.drop_column("runs", name)
