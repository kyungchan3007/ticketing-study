# T-01 (test) US-01~US-04 API 테스트 작성 — RED

## 결과물
- `tests/api/` 아래 테스트(필요하면 `tests/api/conftest.py`).
- 실제 FastAPI 앱(`backend.main.create_app()`)에 요청을 보내 `docs/openapi.yaml`의 경로, 상태 코드, 오류 `code`를 확인한다. 오류 본문은 정확히 `code`, `message` 두 키인지도 확인한다.

## 따를 것
- 요구사항: `docs/PRD.md`, `docs/stories/US-01~04`. 계약: `docs/openapi.yaml`. 접점: `docs/tasks/api-harness.md`.
- 테스트 이름은 `test_us<NN>_ac<NN>_<n>_...` 형식, docstring 첫 줄은 `US-03 / AC-03-2: ...`. (`scripts/story_report.py`가 이 이름으로 스토리별 개수를 센다.)
- 시각은 `app.dependency_overrides[backend.clock.get_now]`로만 다룬다. 테스트 전용 HTTP 경로를 쓰거나 기대하지 않는다.
- 데이터는 테스트마다 `backend.seed.reset(...)`으로 PRD 9절 예시 데이터(P1: A1~A3, P2: B1, 사용자 u1~u10, `T0 = 2026-12-01T10:00:00Z`)를 넣는다.
- 동시성 인수 조건(AC-03-5, AC-04-5, AC-04-6)은 스레드 10개를 barrier로 맞춰 실제로 동시에 보낸다.
- `[열린 질문]` 표시가 제목에 있는 인수 조건(AC-02-4, AC-03-7)과 "열린 질문에 묶인 경우" 목록은 테스트하지 않고 보고에 목록만 적는다.
  - AC-04-8, AC-04-9는 결정된 부분(2xx가 아님, `{code, message}` 두 칸, 좌석 상태 그대로)만 테스트한다. 정확한 상태 코드·code(Q3/Q4)는 확인하지 않는다.
  - AC-04-4의 구매자 확인(Q13), AC-04-5의 나머지 9건 응답 코드(Q1)는 확인하지 않는다.
- `tests/`만 수정한다. `backend/`, `docs/`, `pyproject.toml`은 고치지 않는다(필요하면 lead에게 요청).

## 완료 기준
1. `docker compose`도 `backend/`도 아직 없으므로 `uv run pytest tests/api`가 **실패(RED)** 한다. 실패 이유가 "backend 없음/DB 없음"인 것을 확인한다.
2. lead에게 보고(`rig send dev-lead@tkt`): 만든 파일, 테스트 개수(스토리별), RED 출력 마지막 줄, 건너뛴 인수 조건 목록, 스스로 정한 기술 결정(도구·구조)과 이유 한 줄씩.
3. 보고하고 멈춘다. lead가 해시를 기록한다.
