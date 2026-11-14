"""예매 UNIQUE 위반(uq_bookings_seat)은 서버 고장이 아니라 "이미 팔린 좌석"이다 (T-21)

재현 방법: 좌석 잠금과 SOLD 확인이 있어서 실제 요청만으로는 위반이 안 생긴다. 그래서 일관성이 깨진 데이터를
DB 에 직접 만든다. u1 이 A1 을 홀드해(HELD, 유효한 홀드) 둔 채, 같은 좌석의 옛 홀드와 그 예매 줄을 SQL 로 넣는다.
서버는 좌석이 HELD 이고 홀드가 유효하니 예매 줄을 넣으려다 UNIQUE 를 만난다. 서버 코드·HTTP 경로는 건드리지 않는다.
"""

import psycopg
from fastapi.testclient import TestClient


def _sql(env, query, args=()):
    with psycopg.connect(env.url.replace("postgresql+psycopg", "postgresql"), autocommit=True) as conn:
        return conn.execute(query, args).fetchall() if query.lstrip().lower().startswith("select") else conn.execute(query, args)


def _sold_row_behind_servers_back(env):
    """A1 에 u1 의 유효한 홀드가 있는데, 같은 좌석의 옛 홀드로 만든 예매 줄이 이미 있는 상태를 만들고 hold_id 를 돌려준다."""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    _sql(
        env,
        "insert into holds (hold_id, performance_id, seat_id, user_id, created_at, expires_at)"
        " values ('stale-hold', 'P1', 'A1', 'u9', %s, %s)",
        (env.T0, env.T0),
    )
    _sql(
        env,
        "insert into bookings (hold_id, performance_id, seat_id, user_id, created_at)"
        " values ('stale-hold', 'P1', 'A1', 'u9', %s)",
        (env.T0,),
    )
    return h1


def _bookings(env):
    return _sql(env, "select hold_id, user_id from bookings where performance_id = 'P1' and seat_id = 'A1'")


def test_unique_violation_on_confirm_is_409_seat_already_sold(env):
    """T-21: 확정이 uq_bookings_seat 위반을 만나면 409 SEAT_ALREADY_SOLD {code, message}, 그 좌석의 bookings 줄은 1개 그대로"""
    h1 = _sold_row_behind_servers_back(env)
    env.at(env.t(minutes=1))
    client = TestClient(env.app, raise_server_exceptions=False)
    resp = env.confirm("u1", h1, client=client)
    env.assert_error(resp, 409, "SEAT_ALREADY_SOLD")
    assert _bookings(env) == [("stale-hold", "u9")], "위반 뒤 bookings 줄이 1개(기존 줄)로 그대로여야 한다"


def test_unique_violation_leaves_server_usable(env):
    """T-21: 위반으로 409 를 받은 뒤에도 서버는 다른 좌석의 홀드·확정을 정상 처리한다"""
    h1 = _sold_row_behind_servers_back(env)
    env.at(env.t(minutes=1))
    client = TestClient(env.app, raise_server_exceptions=False)
    env.confirm("u1", h1, client=client)
    h2 = env.hold_ok("u2", "A2")
    env.confirm_ok("u2", h2)
    assert env.statuses("P1")["A2"] == "SOLD"


def test_unique_violation_rolls_back_seat_state(env):
    """T-24 지적 1: uq_bookings_seat 위반 뒤 같은 트랜잭션의 좌석 변경이 되돌아가 A1 은 HELD·current_hold_id 는 u1 의 홀드 그대로, u2 는 홀드할 수 없다"""
    h1 = _sold_row_behind_servers_back(env)
    env.at(env.t(minutes=1))
    client = TestClient(env.app, raise_server_exceptions=False)
    env.assert_error(env.confirm("u1", h1, client=client), 409, "SEAT_ALREADY_SOLD")
    assert env.statuses("P1")["A1"] == "HELD", "좌석맵에서 A1 이 HELD 가 아니다(롤백 안 됨)"
    row = _sql(env, "select status, current_hold_id from seats where performance_id = 'P1' and seat_id = 'A1'")
    assert row == [("HELD", h1)], f"seats 행이 위반 전 그대로가 아니다: {row}"
    env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_HELD")


def test_other_integrity_error_stays_500_internal_error(env):
    """T-24 지적 2: uq_bookings_seat 가 아닌 제약(bookings 기본 키 hold_id, 같은 SQLSTATE 23505) 위반은 500 INTERNAL_ERROR, 좌석은 HELD 그대로이고 A1 의 bookings 줄은 없다"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    # 같은 hold_id 로 다른 좌석(A2)의 예매 줄을 미리 넣어 둔다: 확정이 A1 줄을 넣으면 기본 키(bookings_pkey)가 겹친다.
    _sql(
        env,
        "insert into bookings (hold_id, performance_id, seat_id, user_id, created_at) values (%s, 'P1', 'A2', 'u9', %s)",
        (h1, env.T0),
    )
    env.at(env.t(minutes=1))
    client = TestClient(env.app, raise_server_exceptions=False)
    resp = env.confirm("u1", h1, client=client)
    env.assert_error(resp, 500, "INTERNAL_ERROR")
    assert resp.headers["content-type"].startswith("application/json")
    assert env.statuses("P1")["A1"] == "HELD"
    assert _bookings(env) == [], "A1 의 bookings 줄이 생기면 안 된다"
