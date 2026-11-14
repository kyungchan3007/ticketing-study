"""실제 서버(uvicorn --workers 4) + 테스트 PostgreSQL 로 도는 동시성 테스트 준비 (T-16).

- 서버는 별도 프로세스로 띄운다(빈 포트). 끝나면 프로세스 그룹째 종료해 워커까지 정리한다.
- 시각은 실제 시계. 테스트 전용 HTTP 경로는 없다.
- backend 나 DB 가 없으면 건너뛰지 않고 실패한다.
"""

from __future__ import annotations

import os
import resource
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = "postgresql+psycopg://tkt:tkt@localhost:5432/tkt_test"
WORKERS = 4
SPEC = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))


def operation(operation_id: str):
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and op.get("operationId") == operation_id:
                return path, method.upper(), op
    raise AssertionError(f"계약에 operationId '{operation_id}' 가 없다")


def ok_status(operation_id: str) -> int:
    codes = sorted(int(c) for c in operation(operation_id)[2]["responses"] if str(c).startswith("2"))
    assert len(codes) == 1, f"{operation_id} 의 성공 코드가 하나가 아니다: {codes}"
    return codes[0]


def raise_fd_limit(want: int = 8192) -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = want if hard == resource.RLIM_INFINITY else min(want, hard)
    if soft < target:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))


@pytest.fixture(scope="session")
def db_url():
    try:
        import backend.db
        import backend.seed  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"backend 패키지가 없거나 db/seed 접점이 비어 있다: {exc}")
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
    import psycopg

    try:
        psycopg.connect(url.replace("postgresql+psycopg", "postgresql"), connect_timeout=3).close()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"테스트 DB({url})에 연결할 수 없다. `docker compose up -d --wait` 로 PostgreSQL 을 띄워라: {exc}")
    backend.db.migrate(url)
    return url


@pytest.fixture(scope="session")
def server(db_url, tmp_path_factory):
    """uvicorn backend.main:app --workers 4 를 띄우고 base_url 을 돌려준다."""
    raise_fd_limit()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": db_url}
    log = (tmp_path_factory.mktemp("uvicorn") / "server.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--workers", str(WORKERS),
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            if proc.poll() is not None:
                pytest.fail(f"서버가 시작 중 종료됐다(code {proc.returncode}): {Path(log.name).read_text()}")
            try:
                if httpx.get(base + operation("listPerformances")[0], timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                pytest.fail(f"서버가 30초 안에 준비되지 않았다: {Path(log.name).read_text()}")
            time.sleep(0.2)
        # 워커 4개가 모두 떠 있도록 몇 번 더 부른다.
        for _ in range(20):
            httpx.get(base + operation("listPerformances")[0], timeout=5)
        yield base
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        log.close()
