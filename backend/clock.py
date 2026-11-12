"""현재 시각을 읽는 유일한 곳. 서버는 좌석 잠금 뒤 clock.get_now()를 모듈 경유로 부르고, 테스트는 monkeypatch로 바꿔 끼운다."""

from datetime import datetime, timezone


def get_now() -> datetime:
    return datetime.now(timezone.utc)
