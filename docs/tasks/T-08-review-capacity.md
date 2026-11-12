# T-08 (review) 트래픽 계산 시트 검토 — 가정과 공식만

파일은 수정하지 않는다. 읽기와 `uv run python scripts/capacity.py`, `uv run pytest tests/capacity` 실행만 한다.

## 대상
- `docs/capacity.md` (1절 입력값, 2절 lead가 새로 정한 가정 G1~G8, 3절 공식, 4절 결과)
- `docs/decisions.md`의 [가정 G1]~[가정 G8] 줄(가정의 이유)
- 참고: `scripts/capacity.py`, `tests/capacity/test_capacity.py`

## 확인할 것
1. 가정: 입력값과 모순되거나, 결과를 크게 바꾸는데 빠진 가정이 있는가. 특히 G3(폴링), G6(매진 시 입장 중단), G7(요청이 입장 기간에 고르게 퍼짐), G8(DB에 올리는 작업).
2. 공식: 3절 공식이 2절 가정에서 바르게 나오는가(`N`, `T`, `Wsum`, 폴링 최대, DB 행, API 합계). 적용 조건이 맞는가.
3. 결과: 4절 숫자가 공식대로인가. 가장 큰 초당 요청이 폴링이라는 설명이 맞는가.

## 보고
`rig send dev-lead@tkt`로 표를 보낸다: | 번호 | 심각도(높음/중간/낮음) | 대상(가정 G?/공식/결과) | 내용 | 근거(파일:줄) | 제안 |. 지적이 없으면 "지적 없음"과 확인한 항목. 보고하고 멈춘다.
