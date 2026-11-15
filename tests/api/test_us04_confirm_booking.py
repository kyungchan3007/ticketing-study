"""US-04 예매 요청(결제 대기) (docs/stories/US-04-confirm-booking.md)

예매 요청은 PENDING 예매만 만들고 좌석은 HELD 그대로다. SOLD 는 성공 콜백(US-05)으로 된다.
열린 질문으로 남은 것은 없다(Q1·Q3·Q4·Q13 결정됨).
"""


def test_us04_ac04_1_confirm_own_hold_before_expiry(env):
    """US-04 / AC-04-1: T0 u1 홀드 → T0+4분59초 u1 예매 요청(k1)은 2xx PENDING 에 booking_id, 좌석맵 A1 은 아직 HELD"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=4, seconds=59))
    resp = env.confirm("u1", h1, "k1")
    assert resp.status_code == env.ok_status("confirmBooking"), resp.text
    env.validate(resp.json(), "Booking")
    body = resp.json()
    assert body["booking_id"] and body["status"] == "PENDING", body
    assert body["hold_id"] == h1
    assert env.statuses("P1")["A1"] == "HELD"


def test_us04_ac04_2_expired_hold_cannot_confirm(env):
    """US-04 / AC-04-2: T0 u1 홀드 → T0+5분(경계)·T0+5분1초 u1 예매 요청은 409 HOLD_EXPIRED, 예매 없음, A1 은 SOLD 가 아니고 u2 가 홀드할 수 있다"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=5))
    env.assert_error(env.confirm("u1", h1), 409, "HOLD_EXPIRED")
    env.at(env.t(minutes=5, seconds=1))
    env.assert_error(env.confirm("u1", h1), 409, "HOLD_EXPIRED")
    assert env.booking_rows(hold_id=h1) == [], "만료된 홀드로 예매가 만들어졌다"
    assert env.statuses("P1")["A1"] != "SOLD"
    resp = env.hold("u2", "A1")
    assert resp.status_code == env.ok_status("holdSeat"), resp.text


def test_us04_ac04_2_expiry_judged_after_seat_lock(env):
    """US-04 / AC-04-2 경계(리뷰 #1): 예매 요청이 T0+4분59초를 읽고 좌석 잠금에서 대기하는 사이 T0+5분이 되면 409 HOLD_EXPIRED, 예매 없음"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=4, seconds=59))
    with env.blocked_by_seat_lock(lambda c: env.confirm("u1", h1, client=c)) as result:
        env.at(env.t(minutes=5))
    env.assert_error(result["resp"], 409, "HOLD_EXPIRED")
    assert env.booking_rows(hold_id=h1) == []
    assert env.statuses("P1")["A1"] != "SOLD"


def test_us04_ac04_3_old_hold_after_rehold(env):
    """US-04 / AC-04-3: u1 홀드(T0) 만료 뒤 u2 가 T0+6분에 재홀드 → T0+7분 u1 의 처음 홀드 예매 요청은 409 HOLD_EXPIRED, u2 요청은 2xx PENDING 이고 성공 콜백으로 SOLD"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=6))
    h2 = env.hold_ok("u2", "A1")
    env.at(env.t(minutes=7))
    env.assert_error(env.confirm("u1", h1), 409, "HOLD_EXPIRED")
    booking = env.confirm_ok("u2", h2)
    assert booking["status"] == "PENDING"
    assert env.callback_ok(booking["booking_id"])["status"] == "PAID"
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_4_confirm_sold_seat(env):
    """US-04 / AC-04-4: u1 이 홀드·예매 요청·성공 콜백으로 SOLD 인 A1 을 u2 가 u1 의 홀드로 예매 요청하면 409 SEAT_ALREADY_SOLD"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.pay("u1", h1)
    env.assert_error(env.confirm("u2", h1), 409, "SEAT_ALREADY_SOLD")
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_5_concurrent_confirm_same_booking(env):
    """US-04 / AC-04-5: u1 홀드 후 T0+1분 u1 이 서로 다른 Idempotency-Key 10개로 동시에 예매 요청하면 10건 모두 2xx, booking_id 모두 같음, 그 홀드의 예매는 PENDING 1개"""
    for _ in range(env.rounds):
        env.reset(env.default_performances)
        env.at(env.T0)
        h1 = env.hold_ok("u1", "A1")
        env.at(env.t(minutes=1))
        results = env.run_concurrently([lambda c: env.confirm("u1", h1, client=c) for _ in range(10)])
        codes = [r.status_code for r in results]
        assert codes == [env.ok_status("confirmBooking")] * 10, [(r.status_code, r.text) for r in results]
        ids = {r.json()["booking_id"] for r in results}
        assert len(ids) == 1, f"booking_id 가 하나가 아니다: {ids}"
        rows = env.booking_rows(hold_id=h1)
        assert [(r[0], r[3]) for r in rows] == [(ids.pop(), "PENDING")], rows


def test_us04_ac04_6_hold_then_confirm_race(env):
    """US-04 / AC-04-6: u1~u10 이 각자 홀드→성공하면 예매 요청을 동시에 하면 예매 요청 2xx 정확히 1건, 그 사용자는 홀드 2xx 를 받은 사용자, 성공 콜백 뒤 A1 은 SOLD"""
    for _ in range(env.rounds):
        env.reset(env.default_performances)
        env.at(env.T0)

        def flow(user):
            def run(client):
                held = env.hold(user, "A1", client=client)
                confirmed = None
                if held.status_code == env.ok_status("holdSeat"):
                    confirmed = env.confirm(user, held.json()["hold_id"], client=client)
                return user, held, confirmed

            return run

        outcomes = env.run_concurrently([flow(u) for u in env.users])
        held_ok = [u for u, h, _ in outcomes if h.status_code == env.ok_status("holdSeat")]
        confirmed = [(u, c) for u, _, c in outcomes if c is not None and c.status_code == env.ok_status("confirmBooking")]
        assert len(confirmed) == 1, [(u, h.status_code, c and c.status_code) for u, h, c in outcomes]
        assert confirmed[0][0] in held_ok
        for u, h, _ in outcomes:
            if u not in held_ok:
                assert h.status_code == 409 and h.json()["code"] in {"SEAT_ALREADY_HELD", "SEAT_ALREADY_SOLD"}, h.text
        assert env.statuses("P1")["A1"] == "HELD"
        env.callback_ok(confirmed[0][1].json()["booking_id"])
        assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_7_confirm_requires_user_header(env):
    """US-04 / AC-04-7: T0+1분 X-User-Id 없이 예매 요청하면 401 UNAUTHORIZED, A1 은 여전히 HELD 이고 예매 없음, u1 예매 요청은 2xx"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    env.assert_error(env.confirm(None, h1), 401, "UNAUTHORIZED")
    assert env.statuses("P1")["A1"] == "HELD"
    assert env.booking_rows(hold_id=h1) == []
    env.confirm_ok("u1", h1)


def test_us04_ac04_8_other_users_hold_forbidden(env):
    """US-04 / AC-04-8: u2 가 u1 의 홀드로 예매를 요청하면 403 FORBIDDEN, A1 은 HELD 그대로, 예매 없음, 이어서 u1 예매 요청은 2xx PENDING"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    env.assert_error(env.confirm("u2", h1), 403, "FORBIDDEN")
    assert env.statuses("P1")["A1"] == "HELD"
    assert env.booking_rows(hold_id=h1) == []
    assert env.confirm_ok("u1", h1)["status"] == "PENDING"


def test_us04_ac04_9_confirm_without_hold_not_found(env):
    """US-04 / AC-04-9: 아무도 홀드하지 않은 A1 에 u1 이 없는 hold_id 로 예매를 요청하면 404 NOT_FOUND, A1 은 AVAILABLE 그대로"""
    env.at(env.T0)
    env.assert_error(env.confirm("u1", "no-such-hold"), 404, "NOT_FOUND")
    assert env.statuses("P1")["A1"] == "AVAILABLE"


def test_us04_ac04_10_same_key_same_response(env):
    """US-04 / AC-04-10: T0+1분 키 k1 예매 요청 뒤 T0+2분 같은 홀드·같은 키로 다시 보내면 상태 코드와 본문이 처음과 같고 그 홀드의 예매는 1개"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    first = env.confirm("u1", h1, "k1")
    assert first.status_code == env.ok_status("confirmBooking"), first.text
    assert first.json()["status"] == "PENDING"
    env.at(env.t(minutes=2))
    second = env.confirm("u1", h1, "k1")
    assert (second.status_code, second.json()) == (first.status_code, first.json())
    assert len(env.booking_rows(hold_id=h1)) == 1


def test_us04_ac04_11_paid_booking_returned_for_new_key(env):
    """US-04 / AC-04-11: u1 이 k1 로 예매 요청·성공 콜백으로 PAID 인 뒤 T0+10분 같은 홀드로 새 키 k2 를 보내면 2xx, 같은 booking_id, 상태 PAID, 예매는 1개"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    booking = env.confirm_ok("u1", h1, "k1")
    env.at(env.t(minutes=2))
    assert env.callback_ok(booking["booking_id"])["status"] == "PAID"
    assert env.statuses("P1")["A1"] == "SOLD"
    env.at(env.t(minutes=10))
    again = env.confirm("u1", h1, "k2")
    assert again.status_code == env.ok_status("confirmBooking"), again.text
    assert (again.json()["booking_id"], again.json()["status"]) == (booking["booking_id"], "PAID")
    assert len(env.booking_rows(hold_id=h1)) == 1


def test_us04_ac04_12_missing_idempotency_key(env):
    """US-04 / AC-04-12: u1 이 Idempotency-Key 없이 예매를 요청하면 400 VALIDATION_ERROR, 예매 없음"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.assert_error(env.confirm("u1", h1, None), 400, "VALIDATION_ERROR")
    assert env.booking_rows(hold_id=h1) == []


def test_us04_ac04_13_key_reused_for_other_hold(env):
    """US-04 / AC-04-13: u1 이 A1·A2 를 홀드하고 A1 홀드로 k1 예매 뒤 A2 홀드에 같은 k1 을 쓰면 409 IDEMPOTENCY_KEY_REUSED, A2 홀드의 예매 없음"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    h2 = env.hold_ok("u1", "A2")
    env.confirm_ok("u1", h1, "k1")
    env.assert_error(env.confirm("u1", h2, "k1"), 409, "IDEMPOTENCY_KEY_REUSED")
    assert env.booking_rows(hold_id=h2) == []


def test_us04_ac04_12_missing_key_checked_before_hold_lookup(env):
    """US-04 / AC-04-12(리뷰 T-29 #1): 없는 hold_id 에 Idempotency-Key 도 없으면 404 가 아니라 400 VALIDATION_ERROR(형식 검사가 홀드 조회보다 먼저), X-User-Id 도 없으면 401 이 먼저"""
    env.at(env.T0)
    env.assert_error(env.confirm("u1", "no-such-hold", None), 400, "VALIDATION_ERROR")
    env.assert_error(env.confirm(None, "no-such-hold", None), 401, "UNAUTHORIZED")


def _outcome(resp):
    return resp.status_code, (resp.json().get("code") or resp.json().get("status"))


def test_us04_ac04_13_same_key_two_seats_concurrently(env):
    """US-04 / AC-04-13(리뷰 T-29 #2): u1 이 A1·A2 를 홀드하고 같은 키 k1 로 두 예매 요청을 동시에 보내면 2xx PENDING 정확히 1건, 409 IDEMPOTENCY_KEY_REUSED 1건, 5xx 없음, u1 의 k1 예매 줄 1개"""
    for _ in range(env.rounds):
        env.reset(env.default_performances)
        env.at(env.T0)
        h1, h2 = env.hold_ok("u1", "A1"), env.hold_ok("u1", "A2")
        env.at(env.t(minutes=1))
        results = env.run_concurrently([lambda c, h=h: env.confirm("u1", h, "k1", client=c) for h in (h1, h2)])
        got = sorted(_outcome(r) for r in results)
        assert got == [(200, "PENDING"), (409, "IDEMPOTENCY_KEY_REUSED")], got
        rows = env.sql("select hold_id, status from bookings where user_id = 'u1' and idempotency_key = 'k1'")
        assert len(rows) == 1 and rows[0][1] == "PENDING", rows


def test_us04_ac04_13_same_key_two_seats_overlap_forced(env):
    """US-04 / AC-04-13(리뷰 T-29 #2): 두 요청이 모두 사전 조회를 통과해 같은 (u1, k1) 삽입에서 겹치도록 DB 에서 막은 뒤 풀어도 2xx PENDING 1건, 409 IDEMPOTENCY_KEY_REUSED 1건, 5xx 없음, k1 예매 줄 1개"""
    import threading
    import time

    import psycopg

    env.at(env.T0)
    h1, h2, h3 = env.hold_ok("u1", "A1"), env.hold_ok("u1", "A2"), env.hold_ok("u1", "A3")
    env.at(env.t(minutes=1))
    dsn = env.url.replace("postgresql+psycopg", "postgresql")
    blocker = psycopg.connect(dsn)  # 커밋하지 않은 (u1, k1) 줄: 같은 키를 넣으려는 요청은 여기서 기다린다
    results = {}
    try:
        blocker.execute(
            "insert into bookings (booking_id, hold_id, performance_id, seat_id, user_id, status, idempotency_key, created_at)"
            " values ('blocker', %s, 'P1', 'A3', 'u1', 'PENDING', 'k1', %s)",
            (h3, env.now),
        )

        def send(name, hold):
            results[name] = env.confirm("u1", hold, "k1", client=env.new_client())

        threads = [threading.Thread(target=send, args=(n, h)) for n, h in (("A1", h1), ("A2", h2))]
        for t in threads:
            t.start()
        deadline = time.monotonic() + 10
        with psycopg.connect(dsn, autocommit=True) as watcher:
            while time.monotonic() < deadline:
                waiting = watcher.execute(
                    "select count(*) from pg_stat_activity where wait_event_type = 'Lock'"
                    " and datname = current_database() and pid <> pg_backend_pid()"
                ).fetchone()[0]
                if waiting >= 2:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError(f"두 요청이 같은 (u1, k1) 삽입에서 겹치지 않았다(기다리는 연결 {waiting}개)")
    finally:
        blocker.rollback()  # 줄을 없애고 두 요청을 동시에 푼다
        blocker.close()
        for t in locals().get("threads", []):
            t.join(timeout=30)
    got = sorted(_outcome(r) for r in results.values())
    assert got == [(200, "PENDING"), (409, "IDEMPOTENCY_KEY_REUSED")], got
    rows = env.sql("select hold_id, status from bookings where user_id = 'u1' and idempotency_key = 'k1'")
    assert len(rows) == 1 and rows[0][1] == "PENDING", rows


def _random_key(length):
    """무작위 키. 같은 글자를 반복한 키는 DB 가 압축해서 인덱스 크기 오류가 나지 않으니 압축이 안 되는 키를 쓴다."""
    import secrets

    return secrets.token_hex(length // 2 + 1)[:length]


def _too_long_key_rejected(env, length):
    from fastapi.testclient import TestClient

    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    client = TestClient(env.app, raise_server_exceptions=False)  # 500 이어도 예외가 아니라 응답으로 받는다
    env.assert_error(env.confirm("u1", h1, _random_key(length), client=client), 400, "VALIDATION_ERROR")
    assert env.booking_rows(hold_id=h1) == [], "너무 긴 키로 예매가 만들어졌다"


def test_us04_ac04_14_key_256_chars_rejected(env):
    """US-04 / AC-04-14: 256자 Idempotency-Key 로 예매를 요청하면 400 VALIDATION_ERROR(500·2xx 가 아니다), 예매 없음"""
    _too_long_key_rejected(env, 256)


def test_us04_ac04_14_key_3000_chars_rejected(env):
    """US-04 / AC-04-14: 3000자 Idempotency-Key 로 예매를 요청하면 400 VALIDATION_ERROR(500 이 아니다), 예매 없음"""
    _too_long_key_rejected(env, 3000)


def test_us04_ac04_14_key_255_chars_allowed(env):
    """US-04 / AC-04-14 경계: 255자 Idempotency-Key 로는 2xx PENDING, 같은 키로 다시 보내면 같은 예매"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    key = _random_key(255)
    first = env.confirm_ok("u1", h1, key)
    assert first["status"] == "PENDING"
    assert env.confirm_ok("u1", h1, key)["booking_id"] == first["booking_id"]


def test_us04_ac04_15_same_key_different_users_not_mixed(env):
    """US-04 / AC-04-15: u1(A1)·u2(A2)가 같은 키 k1 로 각자 예매하면 둘 다 2xx PENDING, booking_id 가 다르고 사용자·좌석은 자기 것, 같은 키로 다시 보내면 각자 자기 예매, 동시 출발해도 같다"""
    env.at(env.T0)
    h1, h2 = env.hold_ok("u1", "A1"), env.hold_ok("u2", "A2")
    b1 = env.confirm_ok("u1", h1, "k1")
    b2 = env.confirm_ok("u2", h2, "k1")
    assert b1["status"] == b2["status"] == "PENDING"
    assert b1["booking_id"] != b2["booking_id"]
    assert (b1["hold_id"], b1["seat_id"]) == (h1, "A1") and (b2["hold_id"], b2["seat_id"]) == (h2, "A2")
    owners = {r[0]: r[1] for r in env.sql("select booking_id, user_id from bookings")}
    assert owners == {b1["booking_id"]: "u1", b2["booking_id"]: "u2"}, owners
    assert env.confirm_ok("u1", h1, "k1")["booking_id"] == b1["booking_id"]
    assert env.confirm_ok("u2", h2, "k1")["booking_id"] == b2["booking_id"]


def test_us04_ac04_15_same_key_different_users_concurrently(env):
    """US-04 / AC-04-15: u1(A1)·u2(A2)가 같은 키 k1 로 동시에 예매 요청해도(3번 반복) 둘 다 2xx PENDING, booking_id 가 다르고 각자 자기 홀드의 예매"""
    for _ in range(env.rounds):
        env.reset(env.default_performances)
        env.at(env.T0)
        h1, h2 = env.hold_ok("u1", "A1"), env.hold_ok("u2", "A2")
        r1, r2 = env.run_concurrently(
            [lambda c: env.confirm("u1", h1, "k1", client=c), lambda c: env.confirm("u2", h2, "k1", client=c)]
        )
        assert (r1.status_code, r2.status_code) == (env.ok_status("confirmBooking"),) * 2, (r1.text, r2.text)
        assert r1.json()["booking_id"] != r2.json()["booking_id"]
        assert (r1.json()["hold_id"], r2.json()["hold_id"]) == (h1, h2)
        assert {r1.json()["status"], r2.json()["status"]} == {"PENDING"}


def test_us04_ac04_16_user_id_256_chars_cannot_hold(env):
    """US-04 / AC-04-16: 256자 X-User-Id 로 홀드하면 401 UNAUTHORIZED(2xx 가 아니다), 좌석은 AVAILABLE 그대로, 홀드 없음"""
    env.at(env.T0)
    env.assert_error(env.hold(_random_key(256), "A1"), 401, "UNAUTHORIZED")
    assert env.statuses("P1")["A1"] == "AVAILABLE"
    assert env.sql("select count(*) from holds")[0][0] == 0, "긴 사용자 ID 로 홀드가 만들어졌다"


def test_us04_ac04_16_user_id_3000_chars_cannot_confirm(env):
    """US-04 / AC-04-16: u1 이 만든 홀드를 압축되지 않는 3000자 X-User-Id 로 예매 요청하면 401 UNAUTHORIZED(500·403 이 아니다), 예매 없음, A1 은 HELD 그대로"""
    from fastapi.testclient import TestClient

    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    client = TestClient(env.app, raise_server_exceptions=False)  # 500 이어도 예외가 아니라 응답으로 받는다
    env.assert_error(env.confirm(_random_key(3000), h1, client=client), 401, "UNAUTHORIZED")
    assert env.booking_rows(hold_id=h1) == [], "긴 사용자 ID 로 예매가 만들어졌다"
    assert env.statuses("P1")["A1"] == "HELD"


def test_us04_ac04_16_user_id_3000_chars_owner_cannot_confirm(env):
    """US-04 / AC-04-16(500 경로): 압축되지 않는 3000자 사용자가 소유한 홀드(DB 에 직접 만듦)를 그 사용자가 예매 요청하면 401 UNAUTHORIZED(500 이 아니다), 예매 없음"""
    from fastapi.testclient import TestClient

    env.at(env.T0)
    user = _random_key(3000)
    # 홀드 단계가 긴 ID 를 막기 전에도 500 경로를 볼 수 있게, 긴 사용자의 홀드를 DB 에 직접 만든다.
    env.sql(
        "insert into holds (hold_id, performance_id, seat_id, user_id, created_at, expires_at)"
        " values ('long-user-hold', 'P1', 'A1', %s, %s, %s)",
        (user, env.T0, env.t(minutes=5)),
    )
    env.sql("update seats set status = 'HELD', current_hold_id = 'long-user-hold' where performance_id = 'P1' and seat_id = 'A1'")
    env.at(env.t(minutes=1))
    client = TestClient(env.app, raise_server_exceptions=False)
    env.assert_error(env.confirm(user, "long-user-hold", client=client), 401, "UNAUTHORIZED")
    assert env.booking_rows(hold_id="long-user-hold") == [], "긴 사용자 ID 로 예매가 만들어졌다"


def test_us04_ac04_16_user_id_255_chars_allowed(env):
    """US-04 / AC-04-16 경계: 255자 X-User-Id 로는 홀드 2xx, 예매 요청 2xx PENDING, 그 사용자의 예매로 기록된다"""
    env.at(env.T0)
    user = _random_key(255)
    h1 = env.hold_ok(user, "A1")
    booking = env.confirm_ok(user, h1)
    assert booking["status"] == "PENDING"
    assert env.booking_rows(hold_id=h1)[0][2] == user
