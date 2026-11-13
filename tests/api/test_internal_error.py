"""처리하지 못한 예외의 500 응답 형식 (T-13, PRD 5절 "모든 오류 응답은 {code, message} 두 칸")

DB 에 연결할 수 없는 앱으로 요청을 보낸다. 다른 API 테스트와 달리 DB 가 없는 것이 이 테스트의 조건이므로
env/db_url 픽스처를 쓰지 않는다. 테스트 전용 HTTP 경로는 쓰지 않는다.
"""

import json

import pytest
from fastapi.testclient import TestClient

SECRET = "pw-should-not-leak"
BAD_URL = f"postgresql+psycopg://tktuser:{SECRET}@127.0.0.1:1/nodb"
LEAKS = [SECRET, "127.0.0.1", "nodb", "tktuser", "OperationalError", "psycopg", "sqlalchemy", "Traceback", "Error:"]


@pytest.fixture
def broken_client(monkeypatch):
    """없는 포트의 DB 를 가리키는 앱. 서버 예외를 테스트로 다시 던지지 않고 응답으로 받는다."""
    try:
        import backend.main
    except ImportError as exc:
        pytest.fail(f"backend 패키지가 없거나 backend.main 이 비어 있다: {exc}")
    monkeypatch.setenv("DATABASE_URL", BAD_URL)
    return TestClient(backend.main.create_app(), raise_server_exceptions=False)


def assert_internal_error(resp):
    assert resp.status_code == 500, f"기대 500, 실제 {resp.status_code}: {resp.text}"
    assert resp.headers.get("content-type", "").startswith("application/json"), (
        f"Content-Type 이 application/json 이 아니다: {resp.headers.get('content-type')} / {resp.text}"
    )
    body = json.loads(resp.text)
    assert set(body) == {"code", "message"}, f"본문 키가 code, message 두 칸이 아니다: {body}"
    assert body["code"] == "INTERNAL_ERROR", body
    assert isinstance(body["message"], str) and body["message"], body
    for leak in LEAKS:
        assert leak.lower() not in body["message"].lower(), f"message 에 내부 정보 '{leak}' 가 들어 있다: {body['message']}"


def test_internal_error_list_performances_db_down(broken_client):
    """공통(T-13): DB 에 연결할 수 없을 때 공연 목록은 500 JSON {code: INTERNAL_ERROR, message}, 내부 정보 없음"""
    assert_internal_error(broken_client.get("/performances"))


def test_internal_error_get_seat_map_db_down(broken_client):
    """공통(T-13): DB 에 연결할 수 없을 때 좌석맵은 500 JSON {code: INTERNAL_ERROR, message}, 내부 정보 없음"""
    assert_internal_error(broken_client.get("/performances/P1/seats"))


def test_internal_error_hold_seat_db_down(broken_client):
    """공통(T-13): DB 에 연결할 수 없을 때 홀드(X-User-Id 있음)는 500 JSON {code: INTERNAL_ERROR, message}, 내부 정보 없음"""
    assert_internal_error(broken_client.post("/performances/P1/seats/A1/hold", headers={"X-User-Id": "u1"}))


def test_internal_error_confirm_booking_db_down(broken_client):
    """공통(T-13): DB 에 연결할 수 없을 때 확정(X-User-Id 있음)은 500 JSON {code: INTERNAL_ERROR, message}, 내부 정보 없음"""
    assert_internal_error(broken_client.post("/holds/h1/confirm", headers={"X-User-Id": "u1"}))
