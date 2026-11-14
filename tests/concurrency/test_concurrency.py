"""실제 서버(uvicorn 워커 4개)·PostgreSQL 에서 같은 좌석에 요청이 정말 겹칠 때도 한 번만 팔린다 (T-16)."""

from __future__ import annotations

import asyncio
from collections import Counter

import httpx
import psycopg

from .conftest import ok_status, operation, raise_fd_limit

USERS = 500
CONFIRMS = 20
PERFS = [{"id": "P1", "title": "공연 A", "seats": ["A1", "A2"]}]


async def fire(requests: list[httpx.Request]) -> list[httpx.Response | Exception]:
    """미리 만든 요청들을 한꺼번에 출발시킨다. 연결 수 제한은 요청 수보다 크다."""
    limits = httpx.Limits(max_connections=len(requests) + 50, max_keepalive_connections=0)
    go = asyncio.Event()
    async with httpx.AsyncClient(limits=limits, timeout=60) as client:

        async def one(req):
            await go.wait()
            try:
                return await client.send(req)
            except Exception as exc:  # noqa: BLE001
                return exc

        tasks = [asyncio.create_task(one(r)) for r in requests]
        await asyncio.sleep(0.5)  # 모든 태스크가 출발선에 선다
        go.set()
        return await asyncio.gather(*tasks)


def summarize(results) -> str:
    counts = Counter(
        f"{r.status_code} {r.json().get('code', '') if r.headers.get('content-type', '').startswith('application/json') and isinstance(r.json(), dict) else ''}".strip()
        if isinstance(r, httpx.Response)
        else f"예외 {type(r).__name__}"
        for r in results
    )
    return ", ".join(f"{k}: {v}건" for k, v in sorted(counts.items()))


def prepare(db_url):
    import backend.seed

    backend.seed.reset(db_url, PERFS)


def build(base, operation_id, user, **path_params):
    path, method, _ = operation(operation_id)
    return httpx.Request(method, base + path.format(**path_params), headers={"X-User-Id": user})


def test_concurrent_hold_500_users_one_seat(server, db_url):
    """동시성: 서로 다른 사용자 500명이 같은 좌석을 동시에 홀드하면 201 정확히 1건, 409 SEAT_ALREADY_HELD 499건, 5xx 없음"""
    raise_fd_limit()
    prepare(db_url)
    reqs = [build(server, "holdSeat", f"user{i}", performance_id="P1", seat_id="A1") for i in range(USERS)]
    results = asyncio.run(fire(reqs))
    summary = summarize(results)
    ok = ok_status("holdSeat")
    assert all(isinstance(r, httpx.Response) for r in results), f"응답을 못 받은 요청이 있다: {summary}"
    assert not any(r.status_code >= 500 for r in results), f"5xx 가 있다: {summary}"
    won = [r for r in results if r.status_code == ok]
    held = [r for r in results if r.status_code == 409 and r.json().get("code") == "SEAT_ALREADY_HELD"]
    assert len(won) == 1, f"성공({ok})이 정확히 1건이어야 한다: {summary}"
    assert len(held) == USERS - 1, f"409 SEAT_ALREADY_HELD 가 {USERS - 1}건이어야 한다: {summary}"
    assert len(won) + len(held) == USERS, f"그 밖의 응답이 있다: {summary}"


def test_concurrent_confirm_20_same_hold(server, db_url):
    """동시성: u1 이 홀드한 뒤 같은 hold_id 로 확정 20건이 동시에 오면 성공 1건, 나머지 19건 409, 5xx 없음, bookings 줄은 1개"""
    raise_fd_limit()
    prepare(db_url)
    hold = httpx.Client(timeout=30).send(build(server, "holdSeat", "u1", performance_id="P1", seat_id="A1"))
    assert hold.status_code == ok_status("holdSeat"), hold.text
    hold_id = hold.json()["hold_id"]
    reqs = [build(server, "confirmBooking", "u1", hold_id=hold_id) for _ in range(CONFIRMS)]
    results = asyncio.run(fire(reqs))
    summary = summarize(results)
    ok = ok_status("confirmBooking")
    assert all(isinstance(r, httpx.Response) for r in results), f"응답을 못 받은 요청이 있다: {summary}"
    assert not any(r.status_code >= 500 for r in results), f"5xx 가 있다: {summary}"
    assert sum(r.status_code == ok for r in results) == 1, f"성공({ok})이 정확히 1건이어야 한다: {summary}"
    assert sum(r.status_code == 409 for r in results) == CONFIRMS - 1, f"409 가 {CONFIRMS - 1}건이어야 한다: {summary}"
    with psycopg.connect(db_url.replace("postgresql+psycopg", "postgresql")) as conn:
        n = conn.execute(
            "select count(*) from bookings where performance_id = %s and seat_id = %s", ("P1", "A1")
        ).fetchone()[0]
    assert n == 1, f"bookings 에 A1 줄이 {n}개다(1개여야 한다): {summary}"
