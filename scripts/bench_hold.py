#!/usr/bin/env python3
"""홀드 동시 요청 측정 도구 (docs/concurrency.md 4절).

실제 서버(uvicorn 워커 여러 개)를 띄우고, 경우별로 홀드 요청을 한꺼번에 보내
처리량(배치 전체 시간, 초당 처리 건수)과 응답 시간(요청별 p50·p95, ms), 201·409·5xx 수를 잰다.
라운드마다 데이터를 초기화한다.

경우
  same     같은 좌석 1석에 서로 다른 사용자 500명
  spread   경합 없음: 서로 다른 좌석 100석에 100명(좌석당 1명)
  scatter  좌석 100석에 500명이 흩어져서(좌석당 5명, 사용자 i → 좌석 i % 100)

사용
  uv run python scripts/bench_hold.py                  # 세 경우, 경우마다 10라운드
  uv run python scripts/bench_hold.py --runs 20 --cases same,scatter
  uv run python scripts/bench_hold.py --app-dir /tmp/copy   # 다른 복사본의 backend 로 서버를 띄움

주의
  - 측정은 서버 실행용 DB(tkt_server)로만 한다. 테스트 DB(tkt_test)를 주면 거부한다.
    측정은 이 DB의 데이터를 모두 지우고 다시 넣는다.
  - 테스트와 같은 시각에 돌려도 테스트 DB를 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import resource
import signal
import socket
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "postgresql+psycopg://tkt:tkt@localhost:5432/tkt_server"
PERFORMANCE_ID = "BENCH"
SEATS = [f"S{i:03d}" for i in range(1, 101)]
CASES = {
    # 이름: (설명, 요청 수, 사용자 번호 → 좌석)
    "same": ("같은 좌석에 서로 다른 사용자 500명", 500, lambda i: SEATS[0]),
    "spread": ("경합 없음: 서로 다른 좌석 100석에 100명", 100, lambda i: SEATS[i]),
    "scatter": ("100석에 500명이 흩어져서(좌석당 5명)", 500, lambda i: SEATS[i % len(SEATS)]),
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=10, help="경우마다 측정 라운드 수(기본 10, 워밍업 제외)")
    ap.add_argument("--warmup", type=int, default=1, help="경우마다 버리는 워밍업 라운드 수(기본 1)")
    ap.add_argument("--cases", default="same,spread,scatter", help="쉼표로 구분(same, spread, scatter)")
    ap.add_argument("--workers", type=int, default=4, help="uvicorn 워커 수(기본 4)")
    ap.add_argument("--database-url", default=os.environ.get("BENCH_DATABASE_URL", DEFAULT_URL))
    ap.add_argument("--app-dir", type=Path, default=ROOT, help="서버를 띄울 backend 가 있는 폴더(기본: 이 저장소)")
    args = ap.parse_args()
    if args.database_url.rstrip("/").rsplit("/", 1)[-1] == "tkt_test":
        ap.error("테스트 DB(tkt_test)로는 측정하지 않는다. tkt_server 를 쓴다.")
    unknown = set(args.cases.split(",")) - set(CASES)
    if unknown:
        ap.error(f"모르는 경우: {', '.join(sorted(unknown))}")
    if args.runs < 1:
        ap.error("--runs 는 1 이상")
    return args


def raise_fd_limit(want: int = 8192) -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = want if hard == resource.RLIM_INFINITY else min(want, hard)
    if soft < target:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))


def run_in_app(app_dir: Path, code: str, url: str) -> None:
    """app_dir 의 backend 로 마이그레이션·시드를 한다(서버와 같은 코드를 쓰려고)."""
    subprocess.run([sys.executable, "-c", code, url], cwd=app_dir, check=True,
                   env={**os.environ, "PYTHONPATH": str(app_dir)})


def migrate(app_dir: Path, url: str) -> None:
    run_in_app(app_dir, "import sys; from backend.db import migrate; migrate(sys.argv[1])", url)


RESET_CODE = (
    "import sys; from backend.seed import reset; "
    f"reset(sys.argv[1], [{{'id': {PERFORMANCE_ID!r}, 'title': 'bench', 'seats': {SEATS!r}}}])"
)


def reset(app_dir: Path, url: str) -> None:
    run_in_app(app_dir, RESET_CODE, url)


def start_server(app_dir: Path, url: str, workers: int) -> tuple[subprocess.Popen, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(app_dir)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--workers", str(workers),
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=app_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/performances", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if proc.poll() is not None:
            raise SystemExit("서버가 뜨지 않았다. DB가 떠 있는지(docker compose up -d --wait) 확인하라.")
        time.sleep(0.2)
    else:
        stop_server(proc)
        raise SystemExit("서버가 30초 안에 준비되지 않았다.")
    for _ in range(workers * 5):  # 워커를 모두 데운다
        httpx.get(f"{base}/performances", timeout=5)
    return proc, base


def stop_server(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


async def one_round(base: str, n: int, seat_of) -> tuple[list[float], Counter, float]:
    go = asyncio.Event()
    # 요청마다 새 연결로 보낸다(keep-alive 없음). 연결을 미리 열어 두고 다시 쓰면 그 연결들이 일부 워커에
    # 몰려 붙어서, 워커 4개에 고르게 퍼지지 않고 4~5배 느리게 나왔다(p50 약 1,450ms 대 약 330ms).
    limits = httpx.Limits(max_connections=n + 100, max_keepalive_connections=0)
    async with httpx.AsyncClient(base_url=base, limits=limits, timeout=60) as client:

        ready = 0

        async def hold(i: int):
            nonlocal ready
            path = f"/performances/{PERFORMANCE_ID}/seats/{seat_of(i)}/hold"
            ready += 1
            await go.wait()
            t0 = time.perf_counter()
            try:
                r = await client.post(path, headers={"X-User-Id": f"bench-u{i}"})
                status = r.status_code
            except httpx.HTTPError:
                status = "연결 오류"
            t1 = time.perf_counter()
            return (t1 - t0) * 1000, status, t1

        tasks = [asyncio.create_task(hold(i)) for i in range(n)]
        while ready < n:  # 모든 요청이 출발선에서 기다릴 때까지
            await asyncio.sleep(0.01)
        t_go = time.perf_counter()
        go.set()
        results = await asyncio.gather(*tasks)
    # 배치 전체 시간: 모든 요청이 출발한 순간부터 마지막 응답이 도착한 순간까지.
    batch_ms = (max(t1 for _, _, t1 in results) - t_go) * 1000
    return [ms for ms, _, _ in results], Counter(s for _, s, _ in results), batch_ms


def percentile(values: list[float], q: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def bucket(counts: Counter) -> dict[str, int]:
    out = {"201": 0, "409": 0, "5xx": 0, "기타": 0}
    for status, n in counts.items():
        if status == 201:
            out["201"] += n
        elif status == 409:
            out["409"] += n
        elif isinstance(status, int) and 500 <= status < 600:
            out["5xx"] += n
        else:
            out["기타"] += n
    return out


def measure(app_dir: Path, url: str, base: str, case: str, runs: int, warmup: int) -> dict:
    _, n, seat_of = CASES[case]
    p50s, p95s, buckets, batches = [], [], [], []
    for r in range(warmup + runs):
        reset(app_dir, url)
        latencies, counts, batch_ms = asyncio.run(one_round(base, n, seat_of))
        if r < warmup:
            continue
        p50s.append(percentile(latencies, 50))
        p95s.append(percentile(latencies, 95))
        buckets.append(bucket(counts))
        batches.append(batch_ms)
        print(f"  {case} 라운드 {r - warmup + 1}/{runs}: 전체 {batch_ms:.0f}ms ({n / batch_ms * 1000:.0f}건/초) "
              f"p50 {p50s[-1]:.0f} p95 {p95s[-1]:.0f} {buckets[-1]}",
              file=sys.stderr)
    return {"p50": p50s, "p95": p95s, "buckets": buckets, "batch": batches, "n": n}


def fmt_counts(buckets: list[dict[str, int]], key: str) -> str:
    vals = [b[key] for b in buckets]
    lo, hi = min(vals), max(vals)
    return f"{lo}" if lo == hi else f"{statistics.median(vals):.0f} ({lo}~{hi})"


def main() -> int:
    args = parse_args()
    raise_fd_limit()
    app_dir = args.app_dir.resolve()
    cases = args.cases.split(",")
    migrate(app_dir, args.database_url)
    proc, base = start_server(app_dir, args.database_url, args.workers)
    try:
        results = {c: measure(app_dir, args.database_url, base, c, args.runs, args.warmup) for c in cases}
    finally:
        stop_server(proc)

    db_name = args.database_url.rsplit("/", 1)[-1]
    print(f"측정: 경우마다 워밍업 {args.warmup}회 제외 {args.runs}라운드, 대표값은 라운드 값의 중앙값(괄호는 범위).")
    print(f"서버: uvicorn 워커 {args.workers}개, backend {app_dir}, DB {db_name}. "
          f"기기: {platform.machine()} {platform.system()} {platform.release()}, Python {platform.python_version()}.")
    print()
    print("처리량: 배치 전체 시간 = 모든 요청이 출발한 뒤 마지막 응답까지, 초당 처리 = 요청 수 ÷ 배치 전체 시간.")
    print("응답 시간: 요청 하나하나가 출발해서 응답을 받기까지의 시간(p50·p95).")
    print()
    print("| 경우 | 요청 | 배치 전체(ms) | 초당 처리(건/초) | p50(ms) | p95(ms) | 201 | 409 | 5xx | 기타 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for c in cases:
        r = results[c]
        p50 = f"{statistics.median(r['p50']):.0f} ({min(r['p50']):.0f}~{max(r['p50']):.0f})"
        p95 = f"{statistics.median(r['p95']):.0f} ({min(r['p95']):.0f}~{max(r['p95']):.0f})"
        counts = " | ".join(fmt_counts(r["buckets"], k) for k in ("201", "409", "5xx", "기타"))
        rps = [r["n"] / b * 1000 for b in r["batch"]]
        batch = f"{statistics.median(r['batch']):.0f} ({min(r['batch']):.0f}~{max(r['batch']):.0f})"
        thr = f"{statistics.median(rps):,.0f} ({min(rps):,.0f}~{max(rps):,.0f})"
        print(f"| {CASES[c][0]} | {CASES[c][1]} | {batch} | {thr} | {p50} | {p95} | {counts} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
