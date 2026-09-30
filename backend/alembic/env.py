from alembic import context
from mlstudio.core.config import Settings
from mlstudio.db.base import Base
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
else:
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
