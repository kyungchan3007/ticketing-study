"""예매 UNIQUE 위반(uq_bookings_seat)은 서버 고장이 아니라 "이미 팔린 좌석"이다 (T-21, 6장에서 두 단계에 맞게 옮김)

확정(예매 요청)은 PENDING 줄만 만들어 이제 PAID 를 만들지 않는다. 그래서 uq_bookings_seat(좌석당 PAID 한 줄) 위반은
성공 콜백이 예매를 PAID 로 바꿀 때만 생긴다. 사람이 정한 뜻을 옮기면: 위반이 나면 그 콜백은 2xx 이고 예매는
REFUND_REQUIRED, 좌석은 바뀌지 않는다. 다른 제약의 위반은 지금처럼 500 INTERNAL_ERROR 다.

재현 방법: 좌석 잠금·SOLD 확인이 있어서 실제 요청만으로는 위반이 안 생기므로, 일관성이 깨진 데이터를 DB 에 직접 만든다.
u1 이 A1 을 홀드하고 예매 요청(PENDING b1)을 해 둔 채, 같은 좌석의 옛 홀드와 PAID 예매를 SQL 로 넣는다(좌석은 HELD 그대로).
서버는 좌석이 HELD 이고 홀드가 유효해 b1 을 PAID 로 바꾸려다 UNIQUE 를 만난다. 서버 코드·HTTP 경로는 건드리지 않는다.
"""

from contextlib import contextmanager

from fastapi.testclient import TestClient

STALE_BOOKING = "stale-booking"


def _insert_stale_paid_booking(env, seat="A1"):
    """seat 에 옛 홀드와 그 PAID 예매 줄을 DB 에 직접 넣는다(서버가 모르는 사이에 팔린 것처럼)."""
    env.sql(
        "insert into holds (hold_id, performance_id, seat_id, user_id, created_at, expires_at)"
        " values ('stale-hold', 'P1', %s, 'u9', %s, %s)",
        (seat, env.T0, env.T0),
    )
    env.sql(
        "insert into bookings (booking_id, hold_id, performance_id, seat_id, user_id, status, idempotency_key, created_at)"
        " values (%s, 'stale-hold', 'P1', %s, 'u9', 'PAID', 'stale-key', %s)",
        (STALE_BOOKING, seat, env.T0),
    )


def _pending_booking_with_stale_paid(env):
    """u1 이 A1 홀드·예매 요청(PENDING)을 하고, 같은 좌석에 옛 PAID 줄이 끼어든 상태. (hold_id, booking_id)."""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    b1 = env.confirm_ok("u1", h1)["booking_id"]
    _insert_stale_paid_booking(env)
    return h1, b1


def _seat_row(env):
    return env.sql("select status, current_hold_id from seats where performance_id = 'P1' and seat_id = 'A1'")


def test_unique_violation_on_callback_is_refund_required(env):
    """T-21(6장): 성공 콜백이 uq_bookings_seat 위반을 만나면 2xx REFUND_REQUIRED, 좌석은 HELD 그대로, 그 좌석의 PAID 줄은 기존 1개"""
    h1, b1 = _pending_booking_with_stale_paid(env)
    env.at(env.t(minutes=2))
    client = TestClient(env.app, raise_server_exceptions=False)
    resp = env.callback(b1, "SUCCEEDED", client=client)
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "REFUND_REQUIRED", resp.json()
    assert env.booking_status(b1) == "REFUND_REQUIRED"
    paid = env.booking_rows(seat="A1", statuses=["PAID"])
    assert [(r[0], r[1]) for r in paid] == [(STALE_BOOKING, "stale-hold")], "위반 뒤 PAID 줄이 기존 1개 그대로여야 한다"


def test_unique_violation_rolls_back_seat_state(env):
    """T-24 지적 1(6장): uq_bookings_seat 위반 뒤에도 좌석 변경이 없어 A1 은 HELD·current_hold_id 는 u1 의 홀드 그대로, u2 는 홀드할 수 없다"""
    h1, b1 = _pending_booking_with_stale_paid(env)
    env.at(env.t(minutes=2))
    client = TestClient(env.app, raise_server_exceptions=False)
    resp = env.callback(b1, "SUCCEEDED", client=client)
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert env.statuses("P1")["A1"] == "HELD", "좌석맵에서 A1 이 HELD 가 아니다(좌석이 바뀌었다)"
    assert _seat_row(env) == [("HELD", h1)], f"seats 행이 위반 전 그대로가 아니다: {_seat_row(env)}"
    env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_HELD")


def test_unique_violation_leaves_server_usable(env):
    """T-21(6장): 위반 콜백 뒤에도 서버는 다른 좌석의 홀드·예매 요청·성공 콜백을 정상 처리해 A2 가 SOLD 가 된다"""
    h1, b1 = _pending_booking_with_stale_paid(env)
    env.at(env.t(minutes=2))
    client = TestClient(env.app, raise_server_exceptions=False)
    env.callback(b1, "SUCCEEDED", client=client)
    h2 = env.hold_ok("u2", "A2")
    assert env.pay("u2", h2)["status"] == "PAID"
    assert env.statuses("P1")["A2"] == "SOLD"


@contextmanager
def _one_paid_per_performance(env):
    """테스트 DB 에만 임시로 '공연당 PAID 한 줄' 부분 UNIQUE 인덱스를 둔다(uq_bookings_seat 가 아닌 다른 제약, 같은 SQLSTATE 23505)."""
    env.sql("drop index if exists zz_test_one_paid_per_performance")
    env.sql("create unique index zz_test_one_paid_per_performance on bookings (performance_id) where status = 'PAID'")
    try:
        yield
    finally:
        env.sql("drop index if exists zz_test_one_paid_per_performance")


def test_other_integrity_error_stays_500_internal_error(env):
    """T-24 지적 2(6장): uq_bookings_seat 가 아닌 UNIQUE(같은 23505) 위반으로 성공 콜백이 실패하면 500 INTERNAL_ERROR, 예매는 PENDING·좌석은 HELD 그대로"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    h3 = env.hold_ok("u3", "A3")
    env.at(env.t(minutes=1))
    b1 = env.confirm_ok("u1", h1)["booking_id"]
    b3 = env.confirm_ok("u3", h3)["booking_id"]
    with _one_paid_per_performance(env):
        # A3 가 먼저 PAID 가 되면, A1 의 PAID 는 좌석은 다르지만 임시 제약(공연당 하나)에 걸린다.
        assert env.callback_ok(b3)["status"] == "PAID"
        client = TestClient(env.app, raise_server_exceptions=False)
        env.at(env.t(minutes=2))
        resp = env.callback(b1, "SUCCEEDED", client=client)
    env.assert_error(resp, 500, "INTERNAL_ERROR")
    assert resp.headers["content-type"].startswith("application/json")
    assert env.booking_status(b1) == "PENDING"
    assert env.statuses("P1")["A1"] == "HELD"
    assert _seat_row(env) == [("HELD", h1)]
