#!/usr/bin/env python3
"""트래픽 계산 시트(docs/capacity.md 3절 공식)를 계산한다.

사용: uv run python scripts/capacity.py   # docs/capacity.md 4절에 붙일 마크다운 표 출력
"""

from __future__ import annotations

DEFAULTS: dict[str, float] = {
    "S": 50_000,  # 좌석 수
    "U": 1_000_000,  # 접속 인원
    "A": 60,  # 접속 기간(초)
    "P": 5,  # 폴링 간격(초)
    "R": 200,  # 입장 속도(명/초)
    "v": 2,  # 1인당 좌석 조회
    "h": 2,  # 1인당 홀드
    "p": 0.4,  # 결제 비율
    "k": 1,  # 결제자 1인당 결제
}

ROW_LABELS = {
    "queue_entry": "대기열 진입",
    "queue_poll": "순번 확인(폴링)",
    "seat_view": "좌석 조회",
    "hold": "홀드",
    "payment": "모의 결제",
    "db": "DB 작업",
    "api_total": "API 합계",
}
API_ROWS = ("queue_entry", "queue_poll", "seat_view", "hold", "payment")


def _row(people: float, requests: float, duration_s: float, rps_peak: float) -> dict[str, float]:
    return {
        "people": float(people),
        "requests": float(requests),
        "duration_s": float(duration_s),
        "rps_avg": float(requests) / float(duration_s),
        "rps_peak": float(rps_peak),
    }


def compute(params: dict | None = None) -> dict:
    x = {**DEFAULTS, **(params or {})}
    S, U, A, P, R = x["S"], x["U"], x["A"], x["P"], x["R"]
    v, h, p, k = x["v"], x["h"], x["p"], x["k"]

    N = min(U, S / (p * k))  # 3.1 입장 인원 (G5, G6)
    T = N / R  # 3.1 입장 기간
    if U / A <= R:
        raise ValueError("공식 적용 조건 위반: 접속 속도 U/A 가 입장 속도 R 보다 커야 한다")
    if T < A:
        raise ValueError("공식 적용 조건 위반: 입장 기간 T 가 접속 기간 A 이상이어야 한다")

    Pn = P if U - N > 0 else 0  # 매진 안내 기간(G6): 남은 대기자가 없으면 0
    w_sum = (U / A - R) * A**2 / 2 + U * (T - A) - R * (T**2 - A**2) / 2

    rows = {
        "queue_entry": _row(U, U, A, U / A),
        "queue_poll": _row(U, w_sum / P + (U - N), T + Pn, (U - R * A) / P),  # U - N: 매진 안내 응답(G6)
        "seat_view": _row(N, N * v, T, R * v),
        "hold": _row(N, N * h, T, R * h),
        "payment": _row(N * p, N * p * k, T, R * p * k),
        "db": _row(N, N * (v + h + p * k), T, R * (v + h + p * k)),
    }
    rows["db"]["reads_rps"] = R * v
    rows["db"]["writes_rps"] = R * (h + p * k)
    total_requests = sum(rows[r]["requests"] for r in API_ROWS)
    rows["api_total"] = _row(U, total_requests, T + Pn, sum(rows[r]["rps_peak"] for r in API_ROWS))
    return {"admitted": N, "duration_s": T, "rows": rows}


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def to_markdown(result: dict) -> str:
    lines = [
        f"입장 인원 N = {_fmt(result['admitted'])}명, 입장 기간 T = {_fmt(result['duration_s'])}초",
        "",
        "| 행 | 사람 수 | 요청 수 | 기간(초) | 평균 초당 | 최대 초당 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, label in ROW_LABELS.items():
        r = result["rows"][key]
        lines.append(
            f"| {label} | {_fmt(r['people'])} | {_fmt(r['requests'])} | {_fmt(r['duration_s'])} "
            f"| {_fmt(r['rps_avg'])} | {_fmt(r['rps_peak'])} |"
        )
    db = result["rows"]["db"]
    lines += ["", f"DB 작업 중 읽기 {_fmt(db['reads_rps'])}건/초, 쓰기 트랜잭션 {_fmt(db['writes_rps'])}건/초."]
    return "\n".join(lines)


if __name__ == "__main__":
    print(to_markdown(compute()))
