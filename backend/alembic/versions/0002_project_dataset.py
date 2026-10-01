"""Project and immutable source Dataset metadata.

Revision ID: 0002_project_dataset
Revises: 0001_foundation
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_project_dataset"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("problem_statement", sa.String(), nullable=False),
        sa.Column("success_context", sa.String(), nullable=True),
        sa.Column("ml_objective", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("active_dataset_id", sa.String(36), nullable=True),
        sa.Column("target_column", sa.String(), nullable=True),
        sa.Column("former_targets", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id", "active_dataset_id"],
            ["datasets.project_id", "datasets.id"],
            name="fk_project_active_dataset_owner",
        ),
        sa.CheckConstraint("ml_objective = 'binary_classification'", name="ck_project_objective"),
        sa.CheckConstraint(
            "active_dataset_id IS NOT NULL OR target_column IS NULL",
            name="ck_target_requires_dataset",
        ),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(71), nullable=False),
        sa.Column("source_relative_path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("missing_cells", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("parsing_version", sa.String(32), nullable=False),
        sa.Column("pandas_version", sa.String(32), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "id", name="uq_dataset_owner_id"),
        sa.CheckConstraint("format = 'csv'", name="ck_dataset_format"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])


def downgrade():
    # Break active references before dropping the cyclic owner/reference tables.
    op.execute(sa.text("UPDATE projects SET active_dataset_id = NULL, target_column = NULL"))
    op.drop_table("datasets")
    op.drop_table("projects")
