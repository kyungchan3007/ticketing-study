"""docs/capacity.md 3절 공식대로 scripts/capacity.py 가 계산하는지 검사한다.

기대값은 스크립트를 보지 않고 공식에서 손으로 계산해 적었다.

기본 입력(S=50,000 U=1,000,000 A=60 P=5 R=200 v=2 h=2 p=0.4 k=1):
  N = min(1,000,000, 50,000/0.4) = 125,000      T = N/R = 625초
  Wsum = (16,666.67-200)*60²/2 + 1,000,000*(625-60) - 200*(625²-60²)/2 = 555,937,500 사람·초
  폴링 요청 = Wsum/P + (U-N) = 111,187,500 + 875,000 = 112,062,500   (U-N: 매진 안내 응답, 폴링 기간은 T+P = 630초)
  행            사람        요청          기간  평균/s    최대/s
  대기열 진입   1,000,000   1,000,000     60    16,666.67 16,666.67
  순번 확인     1,000,000   112,062,500   630   177,876.98 197,600
  좌석 조회     125,000     250,000       625   400       400
  홀드          125,000     250,000       625   400       400
  모의 결제     50,000      50,000        625   80        80
  DB 작업       125,000     550,000       625   880       880   (읽기 400, 쓰기 480)
  API 합계      1,000,000   113,612,500   630   180,337.30 215,146.67
"""

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROW_KEYS = {"people", "requests", "duration_s", "rps_avg", "rps_peak"}
ROW_NAMES = {"queue_entry", "queue_poll", "seat_view", "hold", "payment", "db", "api_total"}
ONE_THIRD_M = 1_000_000 / 60  # U / A


def capacity():
    """import 를 테스트 안으로 미룬다: scripts/capacity.py 가 없어도 수집은 되고 테스트마다 FAIL 한다."""
    return importlib.import_module("scripts.capacity")


def compute(params=None):
    return capacity().compute(params)


def approx(value):
    return pytest.approx(value, rel=1e-9)


def check_row(row, people, requests, duration, avg, peak):
    assert row["people"] == approx(people)
    assert row["requests"] == approx(requests)
    assert row["duration_s"] == approx(duration)
    assert row["rps_avg"] == approx(avg)
    assert row["rps_peak"] == approx(peak)


# ---------------------------------------------------------------- 입력값과 형태
def test_defaults_match_section_1():
    """1절 입력값: S, U, A, P, R, v, h, p, k 아홉 개가 문서 값과 같다"""
    assert capacity().DEFAULTS == {"S": 50_000, "U": 1_000_000, "A": 60, "P": 5, "R": 200, "v": 2, "h": 2, "p": 0.4, "k": 1}


def test_compute_result_shape():
    """반환 형태: admitted, duration_s, rows(7개 행 이름, 행마다 다섯 키, db 에는 reads_rps·writes_rps 추가)"""
    result = compute()
    assert set(result) == {"admitted", "duration_s", "rows"}
    assert set(result["rows"]) == ROW_NAMES
    for name, row in result["rows"].items():
        expected = ROW_KEYS | {"reads_rps", "writes_rps"} if name == "db" else ROW_KEYS
        assert set(row) == expected, name


def test_compute_without_params_uses_defaults():
    """params 가 없거나 DEFAULTS 와 같으면 결과가 같고, 호출이 DEFAULTS 를 바꾸지 않는다"""
    defaults = capacity().DEFAULTS
    before = dict(defaults)
    assert compute() == compute(None) == compute(dict(defaults))
    compute({"R": 100})
    assert defaults == before


# ---------------------------------------------------------------- 기본값 공식
def test_default_admitted_and_duration():
    """3.1: N = min(U, S/(p×k)) = 125,000, T = N/R = 625초"""
    result = compute()
    assert result["admitted"] == approx(125_000)
    assert result["duration_s"] == approx(625)


def test_default_row_queue_entry():
    """3.2 대기열 진입: 사람·요청 U, 기간 A, 평균·최대 U/A"""
    check_row(compute()["rows"]["queue_entry"], 1_000_000, 1_000_000, 60, ONE_THIRD_M, ONE_THIRD_M)


def test_default_row_queue_poll():
    """3.2 순번 확인: 요청 Wsum/P+(U-N) = 112,062,500, 기간 T+P = 630, 평균 112,062,500/630, 최대 (U-R×A)/P = 197,600"""
    check_row(compute()["rows"]["queue_poll"], 1_000_000, 112_062_500, 630, 112_062_500 / 630, 197_600)


def test_default_row_seat_view():
    """3.2 좌석 조회: 사람 N, 요청 N×v = 250,000, 평균·최대 R×v = 400"""
    check_row(compute()["rows"]["seat_view"], 125_000, 250_000, 625, 400, 400)


def test_default_row_hold():
    """3.2 홀드: 사람 N, 요청 N×h = 250,000, 평균·최대 R×h = 400"""
    check_row(compute()["rows"]["hold"], 125_000, 250_000, 625, 400, 400)


def test_default_row_payment():
    """3.2 모의 결제: 사람 N×p = 50,000, 요청 N×p×k = 50,000, 평균·최대 R×p×k = 80"""
    check_row(compute()["rows"]["payment"], 50_000, 50_000, 625, 80, 80)


def test_default_row_db():
    """3.2 DB 작업: 요청 N×(v+h+p×k) = 550,000, 평균·최대 880, 읽기 R×v = 400, 쓰기 R×(h+p×k) = 480"""
    row = compute()["rows"]["db"]
    check_row(row, 125_000, 550_000, 625, 880, 880)
    assert row["reads_rps"] == approx(400)
    assert row["writes_rps"] == approx(480)


def test_default_row_api_total():
    """3.2 API 합계: 요청 = 다섯 API 행의 합 113,612,500, 기간 T+P = 630, 평균 113,612,500/630, 최대 = 다섯 행 최대의 합 215,146.67 (DB 행은 제외)"""
    check_row(
        compute()["rows"]["api_total"],
        1_000_000,
        113_612_500,
        630,
        113_612_500 / 630,
        ONE_THIRD_M + 197_600 + 400 + 400 + 80,
    )


# ---------------------------------------------------------------- 입력을 바꿨을 때
def test_changed_R_follows_formulas():
    """R=100: T=1,250초, 좌석 조회·홀드 200, 결제 40, DB 440(읽기 200·쓰기 240), 폴링 요청 229,250,000·기간 1,255·평균 229,250,000/1,255·최대 198,800, API 합계 요청 230,800,000·평균 230,800,000/1,255"""
    result = compute({"R": 100})
    rows = result["rows"]
    assert result["admitted"] == approx(125_000)
    assert result["duration_s"] == approx(1_250)
    check_row(rows["seat_view"], 125_000, 250_000, 1_250, 200, 200)
    check_row(rows["hold"], 125_000, 250_000, 1_250, 200, 200)
    check_row(rows["payment"], 50_000, 50_000, 1_250, 40, 40)
    check_row(rows["db"], 125_000, 550_000, 1_250, 440, 440)
    assert rows["db"]["reads_rps"] == approx(200)
    assert rows["db"]["writes_rps"] == approx(240)
    check_row(rows["queue_poll"], 1_000_000, 229_250_000, 1_255, 229_250_000 / 1_255, 198_800)
    check_row(rows["api_total"], 1_000_000, 230_800_000, 1_255, 230_800_000 / 1_255, ONE_THIRD_M + 198_800 + 200 + 200 + 40)


def test_changed_p_changes_admitted():
    """p=0.2: N = min(U, 50,000/0.2) = 250,000, T = 1,250초, 결제 사람 50,000·평균 40, 좌석 조회 요청 500,000"""
    result = compute({"p": 0.2})
    rows = result["rows"]
    assert result["admitted"] == approx(250_000)
    assert result["duration_s"] == approx(1_250)
    check_row(rows["payment"], 50_000, 50_000, 1_250, 40, 40)
    check_row(rows["seat_view"], 250_000, 500_000, 1_250, 400, 400)


def test_changed_k_scales_payment_and_admitted():
    """k=2: N = 50,000/(0.4×2) = 62,500, T = 312.5초, 결제 사람 25,000·요청 50,000·평균 R×p×k = 160"""
    result = compute({"k": 2})
    assert result["admitted"] == approx(62_500)
    assert result["duration_s"] == approx(312.5)
    check_row(result["rows"]["payment"], 25_000, 50_000, 312.5, 160, 160)
    check_row(result["rows"]["seat_view"], 62_500, 125_000, 312.5, 400, 400)


def test_admitted_capped_by_visitors():
    """S 가 아주 크면 N = U: 입장 1,000,000명, T = 5,000초, 폴링 요청 494,000,000(매진 안내 U-N = 0)·Pn = 0 이라 기간 T = 5,000·평균 98,800·최대 197,600, API 합계 요청 499,400,000·기간 5,000·평균 99,880"""
    result = compute({"S": 1_000_000_000})
    assert result["admitted"] == approx(1_000_000)
    assert result["duration_s"] == approx(5_000)
    check_row(result["rows"]["seat_view"], 1_000_000, 2_000_000, 5_000, 400, 400)
    check_row(result["rows"]["payment"], 400_000, 400_000, 5_000, 80, 80)
    poll = result["rows"]["queue_poll"]
    assert poll["duration_s"] == approx(result["duration_s"]), "N = U 이면 폴링 기간은 정확히 T 다(Pn = 0)"
    assert result["rows"]["api_total"]["duration_s"] == approx(result["duration_s"])
    check_row(poll, 1_000_000, 494_000_000, 5_000, 98_800, 197_600)
    check_row(result["rows"]["api_total"], 1_000_000, 499_400_000, 5_000, 99_880, ONE_THIRD_M + 197_600 + 400 + 400 + 80)


def test_queue_poll_wsum_small_case():
    """Wsum 손계산: U=1,200 A=6 R=100 P=5 S=1,000 p=1 → N=1,000 T=10, Wsum=3,400, 요청 3,400/5+(1,200-1,000) = 880·기간 T+P = 15·평균 880/15·최대 120"""
    result = compute({"U": 1_200, "A": 6, "R": 100, "P": 5, "S": 1_000, "p": 1, "k": 1})
    assert result["admitted"] == approx(1_000)
    assert result["duration_s"] == approx(10)
    check_row(result["rows"]["queue_poll"], 1_200, 880, 15, 880 / 15, 120)


def test_queue_poll_sold_out_notice_requests():
    """매진 안내 응답: 폴링 요청 − Wsum/P = U − N. 기본 875,000, p=0.2 750,000, 소형 케이스 200, N=U(매진 없음)면 0"""
    cases = [
        # (입력, Wsum/P 손계산값, U-N)
        ({}, 111_187_500, 875_000),
        ({"p": 0.2}, 212_750_000, 750_000),
        ({"U": 1_200, "A": 6, "R": 100, "P": 5, "S": 1_000, "p": 1, "k": 1}, 680, 200),
        ({"S": 1_000_000_000}, 494_000_000, 0),
    ]
    for params, wsum_over_p, sold_out_notice in cases:
        poll = compute(params)["rows"]["queue_poll"]
        assert poll["requests"] - wsum_over_p == pytest.approx(sold_out_notice, abs=1e-3), params


def test_boundary_T_equal_A_is_allowed():
    """T == A 는 공식 적용 범위 안이다: S=6,000 p=0.5 → N=12,000, T=60 = A 이면 계산한다"""
    result = compute({"S": 6_000, "p": 0.5})
    assert result["admitted"] == approx(12_000)
    assert result["duration_s"] == approx(60)


# ---------------------------------------------------------------- 공식 적용 조건을 벗어나면 ValueError
def test_value_error_when_arrival_slower_than_admission():
    """U/A < R(접속이 입장보다 느림): U=10,000 이면 ValueError"""
    with pytest.raises(ValueError):
        compute({"U": 10_000})


def test_value_error_when_arrival_equals_admission():
    """U/A == R: U=12,000 이면 ValueError (조건은 U/A > R)"""
    with pytest.raises(ValueError):
        compute({"U": 12_000})


def test_value_error_when_sold_out_before_arrival_ends():
    """T < A(접속이 끝나기 전에 매진): S=1,000 이면 N=2,500, T=12.5 < 60 이므로 ValueError"""
    with pytest.raises(ValueError):
        compute({"S": 1_000})


# ---------------------------------------------------------------- CLI
def test_cli_prints_markdown_table_with_six_row_names():
    """CLI: scripts/capacity.py 가 종료 코드 0, 마크다운 표(| 로 시작하는 줄 8개 이상), 행 이름 6개를 출력한다"""
    proc = subprocess.run(
        [sys.executable, "scripts/capacity.py"], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    for name in ("대기열 진입", "순번 확인", "좌석 조회", "홀드", "모의 결제", "DB 작업"):
        assert name in proc.stdout, f"출력에 행 이름 '{name}' 이 없다"
    table_lines = [line for line in proc.stdout.splitlines() if line.lstrip().startswith("|")]
    assert len(table_lines) >= 8, f"마크다운 표 줄이 8개 미만이다: {len(table_lines)}"
