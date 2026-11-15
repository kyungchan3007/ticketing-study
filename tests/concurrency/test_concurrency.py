"""실제 서버(uvicorn 워커 4개)·PostgreSQL 에서 같은 좌석에 요청이 정말 겹칠 때도 한 번만 팔린다 (T-16)."""

from __future__ import annotations

import asyncio
from collections import Counter

import httpx
import psycopg

from .conftest import ok_status, operation, raise_fd_limit

USERS = 500
CONFIRMS = 20
CALLBACKS = 20
SEATS = 5
CALLBACKS_PER_SEAT = 10
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


def build(base, operation_id, user=None, headers=None, json=None, **path_params):
    path, method, _ = operation(operation_id)
    all_headers = {"X-User-Id": user} if user is not None else {}
    all_headers.update(headers or {})
    return httpx.Request(method, base + path.format(**path_params), headers=all_headers, json=json)


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
    """동시성(US-04 / AC-04-5, 6장): u1 이 홀드한 뒤 같은 hold_id 로 서로 다른 Idempotency-Key 20건을 동시에 보내면 20건 모두 2xx, booking_id 모두 같음, 5xx 없음, 그 홀드의 활성 예매 1줄"""
    raise_fd_limit()
    prepare(db_url)
    hold = httpx.Client(timeout=30).send(build(server, "holdSeat", "u1", performance_id="P1", seat_id="A1"))
    assert hold.status_code == ok_status("holdSeat"), hold.text
    hold_id = hold.json()["hold_id"]
    reqs = [
        build(server, "confirmBooking", "u1", headers={"Idempotency-Key": f"k{i}"}, hold_id=hold_id)
        for i in range(CONFIRMS)
    ]
    results = asyncio.run(fire(reqs))
    summary = summarize(results)
    ok = ok_status("confirmBooking")
    assert all(isinstance(r, httpx.Response) for r in results), f"응답을 못 받은 요청이 있다: {summary}"
    assert not any(r.status_code >= 500 for r in results), f"5xx 가 있다: {summary}"
    assert sum(r.status_code == ok for r in results) == CONFIRMS, f"{CONFIRMS}건 모두 성공({ok})이어야 한다: {summary}"
    ids = {r.json().get("booking_id") for r in results}
    assert len(ids) == 1 and None not in ids, f"booking_id 가 모두 같아야 한다: {ids} / {summary}"
    with psycopg.connect(db_url.replace("postgresql+psycopg", "postgresql")) as conn:
        rows = conn.execute(
            "select booking_id, status from bookings where hold_id = %s and status in ('PENDING', 'PAID')", (hold_id,)
        ).fetchall()
    assert rows == [(ids.pop(), "PENDING")], f"그 홀드의 활성 예매가 PENDING 1줄이어야 한다: {rows} / {summary}"


def test_us05_ac05_7_concurrent_success_callbacks_paid_once(server, db_url):
    """US-05 / AC-05-7: 실제 서버(워커 4개)·실제 시계에서 u1 이 홀드·예매 요청한 PENDING 예매의 성공 콜백 20건이 동시에 오면 20건 모두 2xx PAID, 5xx 없음, A1 은 SOLD, 그 좌석의 PAID 예매 1줄"""
    raise_fd_limit()
    prepare(db_url)
    client = httpx.Client(timeout=30)
    hold = client.send(build(server, "holdSeat", "u1", performance_id="P1", seat_id="A1"))
    assert hold.status_code == ok_status("holdSeat"), hold.text
    booking = client.send(
        build(server, "confirmBooking", "u1", headers={"Idempotency-Key": "k1"}, hold_id=hold.json()["hold_id"])
    )
    assert booking.status_code == ok_status("confirmBooking"), booking.text
    assert "booking_id" in booking.json(), f"예매 요청 응답에 booking_id 가 없다: {booking.text}"
    booking_id = booking.json()["booking_id"]
    reqs = [
        build(server, "paymentCallback", json={"result": "SUCCEEDED"}, booking_id=booking_id) for _ in range(CALLBACKS)
    ]
    results = asyncio.run(fire(reqs))
    summary = summarize(results)
    statuses = Counter(r.json().get("status") if isinstance(r, httpx.Response) and r.status_code < 300 else None for r in results)
    assert all(isinstance(r, httpx.Response) for r in results), f"응답을 못 받은 요청이 있다: {summary}"
    assert not any(r.status_code >= 500 for r in results), f"5xx 가 있다: {summary}"
    ok = ok_status("paymentCallback")
    assert sum(r.status_code == ok for r in results) == CALLBACKS, f"{CALLBACKS}건 모두 {ok} 이어야 한다: {summary}"
    assert statuses == {"PAID": CALLBACKS}, f"응답의 예매 상태가 모두 PAID 여야 한다: {dict(statuses)} / {summary}"
    seatmap = client.send(build(server, "getSeatMap", performance_id="P1"))
    seats = {s["seat_id"]: s["status"] for s in seatmap.json()["seats"]}
    assert seats["A1"] == "SOLD", f"A1 이 SOLD 가 아니다: {seats} / {summary}"
    with psycopg.connect(db_url.replace("postgresql+psycopg", "postgresql")) as conn:
        paid = conn.execute(
            "select count(*) from bookings where performance_id = 'P1' and seat_id = 'A1' and status = 'PAID'"
        ).fetchone()[0]
    assert paid == 1, f"그 좌석의 PAID 예매가 {paid}줄이다(1줄이어야 한다): {summary}"


def test_us05_ac05_7_concurrent_callbacks_many_seats(server, db_url):
    """US-05 / AC-05-7 확장: 실제 서버에서 5석에 각각 홀드·예매 요청을 만든 뒤 좌석마다 같은 성공 콜백 10건(모두 50건)을 한꺼번에 보내면 모든 응답 2xx PAID, 5xx 없음, 좌석마다 SOLD 이고 PAID 예매 1줄"""
    import backend.seed

    raise_fd_limit()
    seats = [f"A{i}" for i in range(1, SEATS + 1)]
    backend.seed.reset(db_url, [{"id": "P1", "title": "공연 A", "seats": seats}])
    client = httpx.Client(timeout=30)
    booking_of = {}
    for i, seat in enumerate(seats, start=1):
        user = f"u{i}"
        hold = client.send(build(server, "holdSeat", user, performance_id="P1", seat_id=seat))
        assert hold.status_code == ok_status("holdSeat"), hold.text
        booking = client.send(
            build(server, "confirmBooking", user, headers={"Idempotency-Key": f"k-{seat}"}, hold_id=hold.json()["hold_id"])
        )
        assert booking.status_code == ok_status("confirmBooking"), booking.text
        assert "booking_id" in booking.json(), f"예매 요청 응답에 booking_id 가 없다: {booking.text}"
        booking_of[seat] = booking.json()["booking_id"]
    reqs, owner = [], []
    for seat in seats:
        for _ in range(CALLBACKS_PER_SEAT):
            reqs.append(build(server, "paymentCallback", json={"result": "SUCCEEDED"}, booking_id=booking_of[seat]))
            owner.append(seat)
    order = list(range(len(reqs)))
    order = order[::CALLBACKS_PER_SEAT] + [i for i in order if i % CALLBACKS_PER_SEAT]  # 좌석이 섞여 출발하도록
    results_in_order = asyncio.run(fire([reqs[i] for i in order]))
    results = [None] * len(reqs)
    for pos, i in enumerate(order):
        results[i] = results_in_order[pos]
    summary = summarize(results)
    assert all(isinstance(r, httpx.Response) for r in results), f"응답을 못 받은 요청이 있다: {summary}"
    assert not any(r.status_code >= 500 for r in results), f"5xx 가 있다: {summary}"
    ok = ok_status("paymentCallback")
    assert all(r.status_code == ok for r in results), f"모두 {ok} 이어야 한다: {summary}"
    bad = Counter(r.json().get("status") for r in results)
    assert bad == {"PAID": len(reqs)}, f"응답의 예매 상태가 모두 PAID 여야 한다: {dict(bad)} / {summary}"
    seatmap = client.send(build(server, "getSeatMap", performance_id="P1")).json()["seats"]
    assert {s["seat_id"]: s["status"] for s in seatmap} == {seat: "SOLD" for seat in seats}, f"{seatmap} / {summary}"
    with psycopg.connect(db_url.replace("postgresql+psycopg", "postgresql")) as conn:
        paid = dict(conn.execute(
            "select seat_id, count(*) from bookings where performance_id = 'P1' and status = 'PAID' group by seat_id"
        ).fetchall())
    assert paid == {seat: 1 for seat in seats}, f"좌석마다 PAID 예매가 1줄이어야 한다: {paid} / {summary}"
