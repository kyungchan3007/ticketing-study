from alembic import context
from sqlalchemy import create_engine, text

from backend.models import Base

config = context.config
target_metadata = Base.metadata

# 동시에 migrate()가 불려도 한 번에 하나만 적용되도록 어드바이저리 락을 건다.
_LOCK_KEY = 7345001


def run_migrations_online() -> None:
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _LOCK_KEY})
        try:
            connection.commit()
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            connection.commit()
    engine.dispose()


run_migrations_online()
