"""Canonical Working Pipeline; migrate the temporary former-target bridge."""

import sqlalchemy as sa

from alembic import op

revision = "0003_working_pipeline"
down_revision = "0002_project_dataset"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "working_pipeline",
            sa.JSON(),
            nullable=False,
            server_default='{"ir_version":"0.1","dataset":null,"target":null,"features":{},"model":null,"split":null}',
        ),
    )
    projects = sa.table(
        "projects",
        sa.column("id", sa.String),
        sa.column("active_dataset_id", sa.String),
        sa.column("target_column", sa.String),
        sa.column("former_targets", sa.JSON),
        sa.column("working_pipeline", sa.JSON),
    )
    datasets = sa.table(
        "datasets",
        sa.column("id", sa.String),
        sa.column("fingerprint", sa.String),
        sa.column("columns", sa.JSON),
    )
    connection = op.get_bind()
    for row in connection.execute(
        sa.select(projects, datasets.c.fingerprint, datasets.c.columns).join(
            datasets, datasets.c.id == projects.c.active_dataset_id
        )
    ).mappings():
        target = row["target_column"]
        ir = {
            "ir_version": "0.1",
            "dataset": {"dataset_id": row["active_dataset_id"], "fingerprint": row["fingerprint"]},
            "target": {
                "column": target,
                "positive_class": None,
                "missing_value_policy": "exclude_rows",
            }
            if target
            else None,
            "features": {
                c["name"]: {"included": c["name"] not in row["former_targets"], "operations": []}
                for c in row["columns"]
                if c["name"] != target
            },
            "model": None,
            "split": None,
        }
        connection.execute(
            projects.update().where(projects.c.id == row["id"]).values(working_pipeline=ir)
        )
    # Native DROP COLUMN avoids rebuilding the cyclic Project/Dataset ownership tables.
    op.drop_column("projects", "former_targets")


def downgrade():
    op.add_column(
        "projects", sa.Column("former_targets", sa.JSON(), nullable=False, server_default="[]")
    )
    # Preserve all current exclusions conservatively in the older role representation.
    projects = sa.table(
        "projects",
        sa.column("id", sa.String),
        sa.column("working_pipeline", sa.JSON),
        sa.column("active_dataset_id", sa.String),
        sa.column("former_targets", sa.JSON),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(projects)).mappings():
        ir = row["working_pipeline"]
        excluded = (
            [name for name, feature in ir["features"].items() if not feature["included"]]
            if (ir["dataset"] and ir["dataset"]["dataset_id"] == row["active_dataset_id"])
            else []
        )
        connection.execute(
            projects.update().where(projects.c.id == row["id"]).values(former_targets=excluded)
        )
    op.drop_column("projects", "working_pipeline")
