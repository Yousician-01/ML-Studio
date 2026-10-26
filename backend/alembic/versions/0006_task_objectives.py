"""Permit explicitly selected regression Projects without rewriting history."""

import sqlalchemy as sa
from alembic.util import CommandError

from alembic import op

revision = "0006_task_objectives"
down_revision = "0005_tracking"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite" and (
        not connection.connection.driver_connection.in_transaction
        or connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0
    ):
        raise CommandError("Objective rebuild requires the checked migration environment.")
    table = sa.Table("projects", sa.MetaData(), autoload_with=connection)
    for column in table.columns:
        if column.server_default is not None:
            # Reflected text() treats :null inside the trusted JSON default as a bind.
            column.server_default = sa.DefaultClause(
                sa.literal_column(str(column.server_default.arg))
            )
    with op.batch_alter_table("projects", recreate="always", copy_from=table) as batch:
        batch.drop_constraint("ck_project_objective", type_="check")
        batch.create_check_constraint(
            "ck_project_objective", "ml_objective IN ('binary_classification', 'regression')"
        )


def downgrade():
    raise CommandError(
        "Downgrade from task objectives is refused. Restore a consistent pre-upgrade backup; "
        "regression Projects must never be silently converted or deleted."
    )
