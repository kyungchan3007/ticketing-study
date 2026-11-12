"""US-03 좌석 홀드 (docs/stories/US-03-hold-seat.md)

AC-03-7(없는 좌석, Q9)과 "열린 질문에 묶인 경우"(Q1·Q2·Q5)는 테스트하지 않는다.
"""


def test_us03_ac03_1_hold_success(env):
    """US-03 / AC-03-1: T0 에 u1 이 A1 을 홀드하면 2xx, 만료 시각 2026-12-01T10:05:00Z, 좌석맵 A1 은 HELD"""
    env.at(env.T0)
    resp = env.hold("u1", "A1")
    assert resp.status_code == env.ok_status("holdSeat"), resp.text
    env.validate(resp.json(), "Hold")
    body = resp.json()
    assert body["expires_at"] == "2026-12-01T10:05:00Z"
    assert (body["performance_id"], body["seat_id"]) == ("P1", "A1")
    assert body["hold_id"]
    assert env.statuses("P1")["A1"] == "HELD"


def test_us03_ac03_2_other_user_blocked_before_expiry(env):
    """US-03 / AC-03-2: T0 u1 홀드 → T0+4분59초 u2 홀드는 409 SEAT_ALREADY_HELD, 홀드는 여전히 u1 의 것(u1 확정 성공)"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=4, seconds=59))
    env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_HELD")
    env.confirm_ok("u1", h1)
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us03_ac03_3_rehold_after_expiry(env):
    """US-03 / AC-03-3: T0 u1 홀드 → T0+5분(경계) u2 홀드는 2xx, 새 만료 2026-12-01T10:10:00Z, 홀드는 u2 의 것"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=5))
    resp = env.hold("u2", "A1")
    assert resp.status_code == env.ok_status("holdSeat"), resp.text
    env.validate(resp.json(), "Hold")
    assert resp.json()["expires_at"] == "2026-12-01T10:10:00Z"
    h2 = resp.json()["hold_id"]
    assert h2 != h1
    env.confirm_ok("u2", h2)
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us03_ac03_3_expiry_judged_after_seat_lock(env):
    """US-03 / AC-03-3 경계(리뷰 #1): u2 홀드가 T0+4분59초를 읽고 좌석 잠금에서 대기하는 사이 T0+5분이 되면 2xx(만료 판단은 잠금 뒤 시각)"""
    env.at(env.T0)
    h1 = env.hold_ok("u1", "A1")
    env.at(env.t(minutes=4, seconds=59))
    with env.blocked_by_seat_lock(lambda c: env.hold("u2", "A1", client=c)) as result:
        env.at(env.t(minutes=5))
    resp = result["resp"]
    assert resp.status_code == env.ok_status("holdSeat"), resp.text
    env.validate(resp.json(), "Hold")
    assert resp.json()["expires_at"] == "2026-12-01T10:10:00Z"
    assert resp.json()["hold_id"] != h1


def test_us03_ac03_4_sold_seat_cannot_be_held(env):
    """US-03 / AC-03-4: u1 이 홀드·확정해 SOLD 인 A1 을 u2 가 홀드하면 409 SEAT_ALREADY_SOLD, T0+1시간 뒤에도 같고 SOLD 유지"""
    env.at(env.T0)
    env.confirm_ok("u1", env.hold_ok("u1", "A1"))
    env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_SOLD")
    assert env.statuses("P1")["A1"] == "SOLD"
    env.at(env.t(hours=1))
    env.assert_error(env.hold("u2", "A1"), 409, "SEAT_ALREADY_SOLD")
    assert env.statuses("P1")["A1"] == "SOLD"


def test_us03_ac03_5_concurrent_hold_exactly_one(env):
    """US-03 / AC-03-5: u1~u10 이 A1 을 동시에 홀드하면 2xx 정확히 1건, 나머지 9건은 409 SEAT_ALREADY_HELD, 성공자만 확정"""
    for _ in range(env.rounds):
        env.reset(env.default_performances)
        env.at(env.T0)
        results = env.run_concurrently([lambda c, u=u: env.hold(u, "A1", client=c) for u in env.users])
        winners = [(u, r) for u, r in zip(env.users, results) if r.status_code == env.ok_status("holdSeat")]
        assert len(winners) == 1, [r.status_code for r in results]
        for u, r in zip(env.users, results):
            if (u, r) not in winners:
                env.assert_error(r, 409, "SEAT_ALREADY_HELD")
        winner, win_resp = winners[0]
        assert env.statuses("P1")["A1"] == "HELD"
        # 성공하지 못한 사용자는 승자의 홀드로 확정할 수 없다(거절).
        loser = next(u for u in env.users if u != winner)
        env.assert_rejected(env.confirm(loser, win_resp.json()["hold_id"]))
        assert env.statuses("P1")["A1"] == "HELD"
        env.confirm_ok(winner, win_resp.json()["hold_id"])
        assert env.statuses("P1")["A1"] == "SOLD"



def test_us03_ac03_6_hold_requires_user_header(env):
    """US-03 / AC-03-6: X-User-Id 없이 홀드하면 401 UNAUTHORIZED, 좌석맵 A1 은 여전히 AVAILABLE"""
    env.at(env.T0)
    env.assert_error(env.hold(None, "A1"), 401, "UNAUTHORIZED")
    assert env.statuses("P1")["A1"] == "AVAILABLE"
