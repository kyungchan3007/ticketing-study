"""API 테스트 공통 준비. docs/tasks/api-harness.md 의 접점을 그대로 따른다.

- 앱: backend.main.create_app()   시각: monkeypatch.setattr(backend.clock, "get_now", ...)
- 데이터: backend.seed.reset(url, performances)   DB 준비: backend.db.migrate(url)
- 경로·성공 코드·본문 형태는 docs/openapi.yaml 에서 읽는다(operationId 로 찾는다).
- backend 가 없거나 DB 에 연결할 수 없으면 건너뛰지 않고 실패한다.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
DEFAULT_URL = "postgresql+psycopg://tkt:tkt@localhost:5432/tkt_test"
T0 = datetime(2026, 12, 1, 10, 0, 0, tzinfo=timezone.utc)
PERFORMANCES = [
    {"id": "P1", "title": "공연 A", "seats": ["A1", "A2", "A3"]},
    {"id": "P2", "title": "공연 B", "seats": ["B1"]},
]
USERS = [f"u{i}" for i in range(1, 11)]


def _operation(operation_id: str):
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and op.get("operationId") == operation_id:
                return path, method, op
    raise AssertionError(f"계약에 operationId '{operation_id}' 가 없다")


class Env:
    """한 테스트가 쓰는 앱·시각·데이터 묶음."""

    T0 = T0
    users = USERS
    default_performances = PERFORMANCES
    rounds = 3  # 동시성 테스트를 같은 테스트 안에서 반복하는 횟수

    def __init__(self, backend, app, url):
        self.backend, self.app, self.url = backend, app, url
        self.now = T0
        self.client = self.new_client()

    # ---- 시각
    def t(self, *, hours=0, minutes=0, seconds=0) -> datetime:
        return T0 + timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def at(self, when: datetime) -> None:
        self.now = when

    # ---- 데이터
    def reset(self, performances) -> None:
        self.backend.seed.reset(self.url, performances)

    # ---- 계약
    def new_client(self) -> TestClient:
        return TestClient(self.app)

    def request(self, operation_id, *, user=None, client=None, json=None, **path_params):
        path, method, _ = _operation(operation_id)
        headers = {"X-User-Id": user} if user is not None else {}
        return (client or self.client).request(method.upper(), path.format(**path_params), headers=headers, json=json)

    def ok_status(self, operation_id) -> int:
        _, _, op = _operation(operation_id)
        codes = sorted(int(c) for c in op["responses"] if str(c).startswith("2"))
        assert len(codes) == 1, f"{operation_id} 의 성공 코드가 하나가 아니다: {codes}"
        return codes[0]

    # ---- 자주 쓰는 요청
    def performances(self, user=None, client=None):
        return self.request("listPerformances", user=user, client=client)

    def seatmap(self, perf="P1", user=None, client=None):
        return self.request("getSeatMap", user=user, client=client, performance_id=perf)

    def statuses(self, perf="P1") -> dict:
        resp = self.seatmap(perf)
        assert resp.status_code == self.ok_status("getSeatMap"), resp.text
        return {s["seat_id"]: s["status"] for s in resp.json()["seats"]}

    def hold(self, user, seat="A1", perf="P1", client=None):
        return self.request("holdSeat", user=user, client=client, performance_id=perf, seat_id=seat)

    def confirm(self, user, hold_id, client=None):
        return self.request("confirmBooking", user=user, client=client, hold_id=hold_id)

    def hold_ok(self, user, seat="A1", perf="P1") -> str:
        """홀드를 걸고 성공을 확인한 뒤 hold_id 를 돌려준다."""
        resp = self.hold(user, seat, perf)
        assert resp.status_code == self.ok_status("holdSeat"), resp.text
        return resp.json()["hold_id"]

    def confirm_ok(self, user, hold_id) -> None:
        resp = self.confirm(user, hold_id)
        assert resp.status_code == self.ok_status("confirmBooking"), resp.text

    # ---- 검사
    def validate(self, body, schema_name: str) -> None:
        schema = {"$ref": f"#/components/schemas/{schema_name}", "components": SPEC["components"]}
        jsonschema.validate(body, schema)

    @staticmethod
    def assert_error(resp, status: int, code: str) -> None:
        assert resp.status_code == status, f"기대 {status}, 실제 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert set(body) == {"code", "message"}, f"오류 본문 키가 code, message 두 칸이 아니다: {body}"
        assert isinstance(body["message"], str)
        assert body["code"] == code, f"기대 code {code}, 실제 {body['code']}"

    @staticmethod
    def assert_rejected(resp) -> None:
        """2xx 가 아닌 오류이고 본문이 정확히 {code, message} 두 칸(상태 코드·code 는 열린 질문)."""
        assert not 200 <= resp.status_code < 300, f"거절돼야 하는데 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert set(body) == {"code", "message"}, f"오류 본문 키가 code, message 두 칸이 아니다: {body}"
        assert isinstance(body["code"], str) and isinstance(body["message"], str)

    # ---- 좌석 잠금 대기 재현
    def _wait_until_lock_waiter(self, timeout=10.0) -> None:
        import psycopg

        with psycopg.connect(self.url.replace("postgresql+psycopg", "postgresql"), autocommit=True) as conn:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                waiting = conn.execute(
                    "select count(*) from pg_stat_activity"
                    " where wait_event_type = 'Lock' and datname = current_database() and pid <> pg_backend_pid()"
                ).fetchone()[0]
                if waiting:
                    return
                time.sleep(0.05)
        raise AssertionError(f"요청이 {timeout:.0f}초 안에 좌석 행 잠금에서 대기하지 않았다")

    @contextmanager
    def blocked_by_seat_lock(self, call, perf="P1", seat="A1"):
        """seed.lock_seat 로 좌석을 잠근 채 call(client) 을 스레드로 보내 잠금 대기가 될 때까지 기다린다.

        with 본문(시각 바꾸기 등)을 실행하고, 본문이 끝나면 잠금을 풀고 응답을 기다려 result["resp"] 에 담는다.
        잠금을 풀기 전에 응답이 오면(막히지 않았으면) 실패한다.
        """
        result: dict = {}

        def target():
            try:
                result["resp"] = call(self.new_client())
            except BaseException as exc:  # noqa: BLE001
                result["error"] = exc

        thread = threading.Thread(target=target)
        try:
            with self.backend.seed.lock_seat(self.url, perf, seat):
                thread.start()
                self._wait_until_lock_waiter()
                assert "resp" not in result, f"잠금을 풀기 전에 응답이 왔다: {result}"
                yield result
                assert "resp" not in result, f"잠금을 풀기 전에 응답이 왔다: {result}"
        finally:
            if thread.ident is not None:
                thread.join(timeout=30)
        assert not thread.is_alive(), "잠금을 푼 뒤에도 요청이 끝나지 않았다"
        if "error" in result:
            raise result["error"]

    # ---- 동시 실행
    def run_concurrently(self, calls):
        """calls: client 하나를 받는 함수 목록. 모두 barrier 앞에서 기다렸다가 동시에 출발한다."""
        n = len(calls)
        barrier = threading.Barrier(n)
        clients = [self.new_client() for _ in calls]
        results, errors = [None] * n, []

        def worker(i):
            try:
                barrier.wait(timeout=15)
                results[i] = calls[i](clients[i])
            except BaseException as exc:  # noqa: BLE001 - 스레드 밖에서 다시 던진다
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=60)
        assert not any(th.is_alive() for th in threads), "동시 요청이 60초 안에 끝나지 않았다(교착 의심)"
        if errors:
            raise errors[0]
        return results


@pytest.fixture(scope="session")
def db_url():
    try:
        import backend.clock  # noqa: F401
        import backend.db  # noqa: F401
        import backend.main  # noqa: F401
        import backend.seed  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"backend 패키지가 없거나 접점(main/clock/db/seed)이 비어 있다: {exc}")
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
    import psycopg

    try:
        psycopg.connect(url.replace("postgresql+psycopg", "postgresql"), connect_timeout=3).close()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"테스트 DB({url})에 연결할 수 없다. `docker compose up -d --wait` 로 PostgreSQL 을 띄워라: {exc}")
    import backend.db

    backend.db.migrate(url)
    return url


@pytest.fixture
def env(db_url, monkeypatch):
    import backend.clock
    import backend.main
    import backend.seed

    monkeypatch.setenv("DATABASE_URL", db_url)
    backend.seed.reset(db_url, PERFORMANCES)
    app = backend.main.create_app()
    environment = Env(backend, app, db_url)
    monkeypatch.setattr(backend.clock, "get_now", lambda: environment.now)
    return environment
