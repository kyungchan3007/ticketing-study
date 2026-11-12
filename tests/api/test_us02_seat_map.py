"""US-02 좌석맵 보기 (docs/stories/US-02-seat-map.md)

AC-02-4(없는 공연, Q9)는 열린 질문이라 테스트하지 않는다.
"""


def test_us02_ac02_1_all_available_without_header(env):
    """US-02 / AC-02-1: 헤더 없이 P1 좌석맵을 요청하면 2xx, 좌석 A1·A2·A3 정확히 3개가 모두 AVAILABLE"""
    resp = env.seatmap("P1")
    assert resp.status_code == env.ok_status("getSeatMap"), resp.text
    env.validate(resp.json(), "SeatMap")
    seats = resp.json()["seats"]
    assert len(seats) == 3
    assert {s["seat_id"]: s["status"] for s in seats} == {"A1": "AVAILABLE", "A2": "AVAILABLE", "A3": "AVAILABLE"}


def test_us02_ac02_2_mixed_states(env):
    """US-02 / AC-02-2: T0 u2 가 A1 홀드, u3 가 A2 홀드·확정 → T0+1분 좌석맵은 A1 HELD, A2 SOLD, A3 AVAILABLE"""
    env.at(env.T0)
    env.hold_ok("u2", "A1")
    env.confirm_ok("u3", env.hold_ok("u3", "A2"))
    env.at(env.t(minutes=1))
    resp = env.seatmap("P1")
    assert resp.status_code == env.ok_status("getSeatMap"), resp.text
    assert env.statuses("P1") == {"A1": "HELD", "A2": "SOLD", "A3": "AVAILABLE"}


def test_us02_ac02_3_other_performance_not_mixed(env):
    """US-02 / AC-02-3: P2 좌석맵에는 좌석이 정확히 1개(B1)뿐이다"""
    resp = env.seatmap("P2")
    assert resp.status_code == env.ok_status("getSeatMap"), resp.text
    assert [s["seat_id"] for s in resp.json()["seats"]] == ["B1"]


def test_us02_ac02_5_with_header_same(env):
    """US-02 / AC-02-5: X-User-Id 가 있어도 응답과 좌석 목록은 AC-02-1 과 같다(2xx, 3개 모두 AVAILABLE)"""
    without = env.seatmap("P1")
    resp = env.seatmap("P1", user="u1")
    assert resp.status_code == env.ok_status("getSeatMap"), resp.text
    assert {s["seat_id"]: s["status"] for s in resp.json()["seats"]} == {
        "A1": "AVAILABLE",
        "A2": "AVAILABLE",
        "A3": "AVAILABLE",
    }
    assert resp.json() == without.json()


def test_us02_ac02_6_expired_hold_shown_available(env):
    """US-02 / AC-02-6: T0 에 잡은 A1 은 T0+4분59초에 HELD, T0+5분(경계)에 AVAILABLE 로 보인다"""
    env.at(env.T0)
    env.hold_ok("u2", "A1")
    env.at(env.t(minutes=4, seconds=59))
    assert env.statuses("P1")["A1"] == "HELD"
    env.at(env.t(minutes=5))
    assert env.statuses("P1")["A1"] == "AVAILABLE"
