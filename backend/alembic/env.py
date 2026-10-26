from alembic import context
from mlstudio import models  # noqa: F401 -- register domain metadata for migration comparison
from mlstudio.core.config import Settings
from mlstudio.db.base import Base
from mlstudio.db.migrations import checked_objective_upgrade, objective_rebuild_pending
from mlstudio.db.session import create_database_engine

settings = context.config.attributes.get("settings") or Settings()

if context.is_offline_mode():
    context.configure(
        url=settings.resolved_database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    destination = context.get_context().opts.get("destination_rev")
    pending = destination is not None and objective_rebuild_pending(
        context.script, destination, context.get_context().get_current_heads()
    )
    if pending:

        def run_checked():
            context.configure(
                connection=connection, target_metadata=Base.metadata, transactional_ddl=True
            )
            with context.begin_transaction():
                context.run_migrations()

        checked_objective_upgrade(connection, run_checked)
    else:
        with context.begin_transaction():
            context.run_migrations()


if not context.is_offline_mode() and context.config.attributes.get("connection") is not None:
    migrate(context.config.attributes["connection"])
elif not context.is_offline_mode():
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
