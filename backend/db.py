import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://tkt:tkt@localhost:5432/tkt"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True)


def migrate(database_url: str) -> None:
    """마이그레이션을 head까지 적용한다. 여러 번 불러도 된다."""
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
