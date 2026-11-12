"""시드 데이터. HTTP 경로가 아니라 파이썬 함수로만 넣는다."""

from contextlib import contextmanager

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.db import database_url, make_engine, migrate
from backend.models import Booking, Hold, Performance, Seat

DEFAULT_PERFORMANCES = [
    {"id": "P1", "title": "공연 A", "seats": [f"A{i}" for i in range(1, 101)]},
]


def reset(database_url: str, performances: list[dict]) -> None:
    """모든 데이터를 지우고 주어진 공연·좌석만 넣는다. 모든 좌석은 AVAILABLE."""
    engine = make_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            # 잠금 대기를 피하려고 TRUNCATE 대신 자식부터 DELETE 한다.
            for model in (Booking, Hold, Seat, Performance):
                session.execute(delete(model))
            for p_index, perf in enumerate(performances):
                session.add(Performance(id=perf["id"], title=perf["title"], position=p_index))
            session.flush()
            for perf in performances:
                for s_index, seat_id in enumerate(perf["seats"]):
                    session.add(
                        Seat(performance_id=perf["id"], seat_id=seat_id, position=s_index, status="AVAILABLE")
                    )
    finally:
        engine.dispose()


@contextmanager
def lock_seat(database_url: str, performance_id: str, seat_id: str):
    """별도 연결에서 서버와 같은 방식(FOR UPDATE)으로 좌석 행을 잠근다. with 블록이 끝나면 놓는다."""
    engine = make_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                select(Seat)
                .where(Seat.performance_id == performance_id, Seat.seat_id == seat_id)
                .with_for_update()
            ).one()
            yield
    finally:
        engine.dispose()


def load_default(database_url: str) -> None:
    """개발용 기본 시드(공연 1개, 좌석 100석)."""
    reset(database_url, DEFAULT_PERFORMANCES)


if __name__ == "__main__":
    url = database_url()
    migrate(url)
    load_default(url)
    print(f"기본 시드를 넣었다: {url}")
