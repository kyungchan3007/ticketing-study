# T-07 (test) 트래픽 계산 테스트 작성 — 실패(FAIL)

## 결과물
- `tests/capacity/test_capacity.py`: `docs/capacity.md` 3절 공식대로 `scripts/capacity.py`의 결과를 검증한다.

## 계산 스크립트 접점 (lead가 만든다)
- `from scripts.capacity import DEFAULTS, compute`
- `DEFAULTS`: 1절 입력값 dict. 키는 `S, U, A, P, R, v, h, p, k`.
- `compute(params: dict | None = None) -> dict`: `params`가 없으면 `DEFAULTS`. 일부 키만 주면 나머지는 `DEFAULTS`.
  - 반환: `{"admitted": N, "duration_s": T, "rows": {...}}`
  - `rows`의 키: `queue_entry`, `queue_poll`, `seat_view`, `hold`, `payment`, `db`, `api_total`
  - 각 행: `{"people": float, "requests": float, "duration_s": float, "rps_avg": float, "rps_peak": float}`
  - `db` 행에는 `"reads_rps"`, `"writes_rps"`도 있다.
  - `U / A ≤ R`이거나 `T < A`이면 `ValueError`.
- 값은 반올림하지 않은 float이다. 테스트는 `pytest.approx`로 비교한다.
- CLI: `uv run python scripts/capacity.py`가 4절에 붙일 마크다운 표를 출력하고 종료 코드 0.

## 할 일
1. 기본 입력값으로 행마다 사람 수·요청 수·기간·평균·최대 초당이 3절 공식과 같은지 확인한다. 기대값은 공식에서 직접 계산해 테스트에 적는다(스크립트 코드를 보고 베끼지 않는다).
2. 입력을 바꿨을 때(예: `p` 또는 `R` 변경)도 공식대로 바뀌는지 1개 이상 확인한다.
3. 공식 적용 조건을 벗어나면 `ValueError`인지 확인한다.
4. CLI가 종료 코드 0이고 행 이름 6개(대기열 진입, 순번 확인, 좌석 조회, 홀드, 모의 결제, DB 작업)를 출력하는지 확인한다.
5. `tests/`만 수정한다.

## 완료 기준
- `scripts/capacity.py`가 아직 없어서 `uv run pytest tests/capacity`가 실패(FAIL)한다. 이유를 확인한다.
- lead에게 보고: 파일, 테스트 개수, 실패 출력 마지막 줄과 이유, 공식에서 계산한 기본값 기대치(N, T, 행별 평균·최대 초당), 공식이 모호해서 테스트로 옮기기 어려운 곳, 기술 결정 한 줄씩. 보고하고 멈춘다.
