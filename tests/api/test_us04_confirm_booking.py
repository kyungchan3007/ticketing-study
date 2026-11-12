"""US-04 모의 결제로 예매 확정 (docs/stories/US-04-confirm-booking.md)

확인하지 않는 것(열린 질문):
- AC-04-4 의 구매자 확인(Q13)
- AC-04-5 의 나머지 9건 응답 코드(Q1)
- AC-04-8, AC-04-9 의 정확한 상태 코드와 code(Q3, Q4). 거절됨·두 칸 본문·좌석 상태만 확인한다.
"""


def test_us04_ac04_1_confirm_own_hold_before_expiry(env):
    """US-04 / AC-04-1: T0 u1 홀드 → T0+4분59초 u1 확정은 2xx, 좌석맵 A1 은 SOLD"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=4, seconds=59))
    resp = env.confirm("u1", h1)
    assert resp.status_code == env.ok_status("confirmBooking"), resp.text
    env.validate(resp.json(), "Confirmation")
    assert resp.json()["hold_id"] == h1
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_2_expired_hold_cannot_confirm(env):
    """US-04 / AC-04-2: T0 u1 홀드 → T0+5분(경계) u1 확정은 409 HOLD_EXPIRED, A1 은 SOLD 가 아니고 u2 가 홀드할 수 있다"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=5))
    env.assert_error(env.confirm("u1", h1), 409, "HOLD_EXPIRED")
    assert env.statuses("P1")["A1"] != "SOLD"
    resp = env.hold("u2", "A1")
    assert resp.status_code == env.ok_status("holdSeat"), resp.text


def test_us04_ac04_2_expiry_judged_after_seat_lock(env):
    """US-04 / AC-04-2 경계(리뷰 #1): 확정 요청이 T0+4분59초를 읽고 좌석 잠금에서 대기하는 사이 T0+5분이 되면 409 HOLD_EXPIRED, A1 은 SOLD 가 아니다"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=4, seconds=59))
    with env.blocked_by_seat_lock(lambda c: env.confirm("u1", h1, client=c)) as result:
        env.at(env.t(minutes=5))
    env.assert_error(result["resp"], 409, "HOLD_EXPIRED")
    assert env.statuses("P1")["A1"] != "SOLD"


def test_us04_ac04_3_old_hold_after_rehold(env):
    """US-04 / AC-04-3: u1 홀드(T0) 만료 뒤 u2 가 T0+6분에 재홀드 → T0+7분 u1 의 처음 홀드 확정은 409 HOLD_EXPIRED, u2 확정은 2xx 로 SOLD"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=6))
    h2 = env.hold_ok("u2", "A1")
    env.at(env.t(minutes=7))
    env.assert_error(env.confirm("u1", h1), 409, "HOLD_EXPIRED")
    env.confirm_ok("u2", h2)
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_4_confirm_sold_seat(env):
    """US-04 / AC-04-4: u1 이 홀드·확정해 SOLD 인 A1 을 u2 가 확정하려 하면 409 SEAT_ALREADY_SOLD (구매자 확인은 Q13 대기)"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.confirm_ok("u1", h1)
    env.assert_error(env.confirm("u2", h1), 409, "SEAT_ALREADY_SOLD")
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_5_concurrent_confirm_sold_once(env):
    """US-04 / AC-04-5: u1 홀드 후 T0+1분에 u1 의 확정 10건이 동시에 오면 2xx 최소 1건, 서버 오류 없음, A1 은 SOLD 이고 다시 팔리지 않는다"""
    for _ in range(env.rounds):
        env.reset(env.default_performances)
        env.at(env.T0)
        h1 = env.hold_ok("u1", "A1")
        env.at(env.t(minutes=1))
        results = env.run_concurrently([lambda c: env.confirm("u1", h1, client=c) for _ in range(10)])
        codes = [r.status_code for r in results]
        assert any(200 <= c < 300 for c in codes), codes
        assert all(c < 500 for c in codes), codes
        assert env.statuses("P1")["A1"] == "SOLD"
        # SOLD 는 한 번: 이후 누구도 다시 홀드할 수 없다.
        env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_SOLD")



def test_us04_ac04_6_hold_then_confirm_race(env):
    """US-04 / AC-04-6: u1~u10 이 각자 홀드→성공하면 확정을 동시에 하면 확정 2xx 정확히 1건, 그 사용자는 홀드 2xx 를 받은 사용자, A1 은 SOLD"""
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
        confirmed_ok = [
            u for u, _, c in outcomes if c is not None and c.status_code == env.ok_status("confirmBooking")
        ]
        assert len(confirmed_ok) == 1, [(u, h.status_code, c and c.status_code) for u, h, c in outcomes]
        assert confirmed_ok[0] in held_ok
        for u, h, _ in outcomes:
            if u not in held_ok:
                assert h.status_code == 409 and h.json()["code"] in {"SEAT_ALREADY_HELD", "SEAT_ALREADY_SOLD"}, h.text
        assert env.statuses("P1")["A1"] == "SOLD"



def test_us04_ac04_7_confirm_requires_user_header(env):
    """US-04 / AC-04-7: T0+1분 X-User-Id 없이 확정하면 401 UNAUTHORIZED, A1 은 여전히 HELD 이고 u1 확정은 2xx"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    env.assert_error(env.confirm(None, h1), 401, "UNAUTHORIZED")
    assert env.statuses("P1")["A1"] == "HELD"
    env.confirm_ok("u1", h1)


def test_us04_ac04_8_other_users_hold_rejected(env):
    """US-04 / AC-04-8: u2 가 u1 의 홀드로 확정하면 2xx 가 아닌 {code, message} 오류, A1 은 HELD 그대로, 이어서 u1 확정은 2xx 로 SOLD"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=1))
    env.assert_rejected(env.confirm("u2", h1))
    assert env.statuses("P1")["A1"] == "HELD"
    env.confirm_ok("u1", h1)
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us04_ac04_9_confirm_without_hold_rejected(env):
    """US-04 / AC-04-9: 아무도 홀드하지 않은 A1 을 u1 이 확정하려 하면 2xx 가 아닌 {code, message} 오류, A1 은 AVAILABLE 그대로"""
    env.at(env.T0)
    env.assert_rejected(env.confirm("u1", "no-such-hold"))
    assert env.statuses("P1")["A1"] == "AVAILABLE"
