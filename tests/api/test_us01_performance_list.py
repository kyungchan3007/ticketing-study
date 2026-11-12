"""US-01 공연 목록 보기 (docs/stories/US-01-performance-list.md)"""


def _pairs(resp):
    return {(p["id"], p["title"]) for p in resp.json()["performances"]}


def test_us01_ac01_1_list_without_header(env):
    """US-01 / AC-01-1: 헤더 없이 공연 목록을 요청하면 2xx, 공연 P1·P2 정확히 2개(ID와 제목)"""
    resp = env.performances()
    assert resp.status_code == env.ok_status("listPerformances"), resp.text
    env.validate(resp.json(), "PerformanceList")
    assert len(resp.json()["performances"]) == 2
    assert _pairs(resp) == {("P1", "공연 A"), ("P2", "공연 B")}


def test_us01_ac01_2_list_empty(env):
    """US-01 / AC-01-2: 공연이 하나도 없으면 2xx, 목록은 빈 배열"""
    env.reset([])
    resp = env.performances()
    assert resp.status_code == env.ok_status("listPerformances"), resp.text
    assert resp.json()["performances"] == []


def test_us01_ac01_3_list_with_header_same(env):
    """US-01 / AC-01-3: X-User-Id 가 있어도 응답과 목록은 헤더 없을 때와 같다"""
    without = env.performances()
    with_header = env.performances(user="u1")
    assert with_header.status_code == env.ok_status("listPerformances"), with_header.text
    assert _pairs(with_header) == {("P1", "공연 A"), ("P2", "공연 B")}
    assert with_header.status_code == without.status_code
    assert with_header.json() == without.json()
