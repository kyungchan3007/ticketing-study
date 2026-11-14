import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://tkt:tkt@localhost:5432/tkt_server"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


# 워커 하나가 열 수 있는 연결 수는 POOL_SIZE + MAX_OVERFLOW 이다. 아래 식이 성립해야 한다:
#   서버 인스턴스 수 × 워커 수 × (POOL_SIZE + MAX_OVERFLOW) ≤ PostgreSQL max_connections(기본 100)
# (인스턴스 1개, 워커 4개면 4 × 15 = 60, 나머지는 마이그레이션·관리용 여유).
# 한도를 넘는 요청은 연결이 반납될 때까지 풀에서 기다린다(pool_timeout).
POOL_SIZE = 10
MAX_OVERFLOW = 5


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW, pool_pre_ping=True)


def migrate(database_url: str) -> None:
    """마이그레이션을 head까지 적용한다. 여러 번 불러도 된다."""
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
