"""US-05 모의 결제 콜백 (docs/stories/US-05-payment-callback.md)

공통 준비: T0 u1 이 A1 홀드, T0+1분 예매 요청 → PENDING 예매 b1. AC-05-7(실제 서버 동시 콜백)은 tests/concurrency 에 있다.
"""

BAD_BODIES = [{}, {"result": "MAYBE"}, {"result": None}, {"result": "succeeded"}, {"outcome": "SUCCEEDED"}]


def prepared(env):
    """공통 준비. (hold_id, booking_id)."""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    booking = env.confirm_ok("u1", h1)
    assert booking["status"] == "PENDING"
    return h1, booking["booking_id"]


def test_us05_ac05_1_success_before_expiry_sells_seat(env):
    """US-05 / AC-05-1: T0+4분59초 b1 의 성공 콜백은 2xx PAID, 좌석맵 A1 은 SOLD"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=4, seconds=59))
    resp = env.callback(b1, "SUCCEEDED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    env.validate(resp.json(), "Booking")
    assert (resp.json()["booking_id"], resp.json()["status"]) == (b1, "PAID")
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us05_ac05_2_success_at_expiry_needs_refund(env):
    """US-05 / AC-05-2: T0+5분(경계) b1 의 성공 콜백은 2xx REFUND_REQUIRED, A1 은 AVAILABLE(SOLD 아님), 이어서 u2 가 A1 을 홀드하면 2xx"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=5))
    resp = env.callback(b1, "SUCCEEDED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "REFUND_REQUIRED", resp.json()
    assert env.statuses("P1")["A1"] == "AVAILABLE"
    held = env.hold("u2", "A1")
    assert held.status_code == env.ok_status("holdSeat"), held.text


def test_us05_ac05_2_success_after_expiry_needs_refund(env):
    """US-05 / AC-05-2: T0+5분1초에 처음 온 b1 의 성공 콜백도 2xx REFUND_REQUIRED, A1 은 SOLD 가 아니다"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=5, seconds=1))
    resp = env.callback(b1, "SUCCEEDED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "REFUND_REQUIRED", resp.json()
    assert env.statuses("P1")["A1"] != "SOLD"


def test_us05_ac05_2_expiry_judged_after_seat_lock(env):
    """US-05 / AC-05-2 경계: 성공 콜백이 T0+4분59초를 읽고 좌석 잠금에서 대기하는 사이 T0+5분이 되면 REFUND_REQUIRED, A1 은 SOLD 가 아니다(시각은 잠금 뒤에 읽는다)"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=4, seconds=59))
    with env.blocked_by_seat_lock(lambda c: env.callback(b1, "SUCCEEDED", client=c)) as result:
        env.at(env.t(minutes=5))
    resp = result["resp"]
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "REFUND_REQUIRED", resp.json()
    assert env.statuses("P1")["A1"] != "SOLD"
    assert env.booking_status(b1) == "REFUND_REQUIRED"


def test_us05_ac05_3_late_success_after_rehold(env):
    """US-05 / AC-05-3: u2 가 T0+6분 재홀드한 뒤 T0+7분 b1 의 성공 콜백은 REFUND_REQUIRED, A1 은 HELD 이고 u2 의 홀드(u2 예매 요청 2xx)"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=6))
    h2 = env.hold_ok("u2", "A1")
    env.at(env.t(minutes=7))
    resp = env.callback(b1, "SUCCEEDED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "REFUND_REQUIRED", resp.json()
    assert env.statuses("P1")["A1"] == "HELD"
    assert env.confirm_ok("u2", h2)["status"] == "PENDING"


def test_us05_ac05_4_failed_callback_keeps_hold(env):
    """US-05 / AC-05-4: T0+2분 b1 실패 콜백은 2xx FAILED, A1 은 HELD(u2 홀드 409), T0+3분 u1 새 키 예매 요청은 새 PENDING, T0+4분 그 성공 콜백으로 SOLD"""
    h1, b1 = prepared(env)
    env.at(env.t(minutes=2))
    resp = env.callback(b1, "FAILED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "FAILED", resp.json()
    assert env.statuses("P1")["A1"] == "HELD"
    env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_HELD")
    env.at(env.t(minutes=3))
    second = env.confirm_ok("u1", h1)
    assert second["booking_id"] != b1 and second["status"] == "PENDING", second
    env.at(env.t(minutes=4))
    assert env.callback_ok(second["booking_id"])["status"] == "PAID"
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us05_ac05_4_failed_then_new_request_rows(env):
    """US-05 / AC-05-4: b1 실패 콜백 뒤 u1 이 새 키로 다시 예매를 요청하면 그 좌석의 예매는 DB 에서 FAILED 1개(b1)와 PENDING 1개"""
    h1, b1 = prepared(env)
    env.at(env.t(minutes=2))
    assert env.callback_ok(b1, "FAILED")["status"] == "FAILED"
    env.at(env.t(minutes=3))
    b2 = env.confirm_ok("u1", h1)["booking_id"]
    rows = env.booking_rows(seat="A1")
    assert [(r[0], r[3]) for r in rows] == [(b1, "FAILED"), (b2, "PENDING")], rows


def test_us05_ac05_5_duplicate_callback_applied_once(env):
    """US-05 / AC-05-5: T0+2분 성공 콜백으로 PAID 인 b1 에 T0+3분 성공 콜백이 또 오면 2xx PAID 그대로, A1 은 SOLD, 그 좌석의 PAID 예매는 1개"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=2))
    assert env.callback_ok(b1)["status"] == "PAID"
    env.at(env.t(minutes=3))
    resp = env.callback(b1, "SUCCEEDED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "PAID"
    assert env.statuses("P1")["A1"] == "SOLD"
    assert len(env.booking_rows(seat="A1", statuses=["PAID"])) == 1


def test_us05_ac05_6_finished_booking_ignores_other_result(env):
    """US-05 / AC-05-6: PAID 인 b1 에 T0+3분 실패 콜백이 와도 2xx PAID 그대로·A1 SOLD, 반대로 FAILED 뒤 성공 콜백이 와도 FAILED 그대로이고 좌석은 팔리지 않는다"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=2))
    assert env.callback_ok(b1)["status"] == "PAID"
    env.at(env.t(minutes=3))
    resp = env.callback(b1, "FAILED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "PAID"
    assert env.statuses("P1")["A1"] == "SOLD"
    # 반대 순서: 새 데이터에서 실패 → 성공
    env.reset(env.default_performances)
    _, b2 = prepared(env)
    env.at(env.t(minutes=2))
    assert env.callback_ok(b2, "FAILED")["status"] == "FAILED"
    env.at(env.t(minutes=3))
    resp = env.callback(b2, "SUCCEEDED")
    assert resp.status_code == env.ok_status("paymentCallback"), resp.text
    assert resp.json()["status"] == "FAILED"
    assert env.statuses("P1")["A1"] != "SOLD"


def test_us05_ac05_8_callback_for_unknown_booking(env):
    """US-05 / AC-05-8: 콜백 경로가 있는 서버에서(진짜 예매 b1 의 콜백은 2xx) 없는 booking_id 로 성공 콜백이 오면 404 NOT_FOUND {code, message}"""
    _, b1 = prepared(env)
    # 경로 자체가 없어서 나는 404 와 구별하려고, 먼저 진짜 예매의 콜백이 처리되는 것을 확인한다.
    env.at(env.t(minutes=2))
    env.callback_ok(b1)
    env.assert_error(env.callback("no-such-booking", "SUCCEEDED"), 404, "NOT_FOUND")


def test_us05_ac05_9_invalid_result_rejected(env):
    """US-05 / AC-05-9: 결과가 없거나 SUCCEEDED·FAILED 가 아닌 콜백은 400 VALIDATION_ERROR, 본문이 없어도 같고, b1 은 PENDING 그대로"""
    _, b1 = prepared(env)
    env.at(env.t(minutes=2))
    for body in BAD_BODIES + [None]:
        env.assert_error(env.callback(b1, body=body), 400, "VALIDATION_ERROR")
    assert env.booking_status(b1) == "PENDING"
    assert env.statuses("P1")["A1"] == "HELD"
