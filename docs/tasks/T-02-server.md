# T-02 (server) 계약대로 첫 서버 구현 — GREEN

## 결과물
- `backend/`: FastAPI + PostgreSQL(SQLAlchemy, Alembic) 구현. `docs/openapi.yaml`의 네 operation(`listPerformances`, `getSeatMap`, `holdSeat`, `confirmBooking`).
- 루트 `docker-compose.yml`: PostgreSQL(헬스체크 포함). 처음 뜰 때 `tkt`, `tkt_test` 두 DB를 만든다. 이 작업에 한해 루트 `docker-compose.yml`과 그것이 쓰는 초기화 파일을 server가 만든다.
- 테이블 마이그레이션(Alembic)과 시드: 공연 1개, 좌석 100석(`backend.seed.load_default`).

## 따를 것
- 요구사항: `docs/PRD.md`, `docs/stories/`. 계약: `docs/openapi.yaml`. **접점: `docs/tasks/api-harness.md`(함수 이름·시그니처 그대로).**
- 의존성은 이미 `pyproject.toml`에 있다: fastapi, uvicorn, sqlalchemy, alembic, psycopg[binary], (dev) httpx. 더 필요하면 lead에게 요청.
- 좌석 하나는 한 번만 팔린다(동시 요청 포함). 홀드·확정 판단과 상태 변경은 한 트랜잭션 안에서 잠금을 잡고 한다.
- 시각은 `backend.clock.get_now`로만 읽는다(`Depends(get_now)`).
- 모든 오류 응답은 `{code, message}` 두 칸. FastAPI 기본 오류(422 등)가 이 형식을 깨지 않게 한다. `X-User-Id`가 없으면 422가 아니라 401 `UNAUTHORIZED`.
- **테스트 파일(`tests/`)은 고치지 않는다.** 테스트 전용 HTTP 경로를 만들지 않는다.

## 완료 기준
1. `docker compose up -d --wait` 후 `uv run pytest` 전체 통과, `uv run python scripts/story_report.py` 실패 0.
2. lead에게 보고(`rig send dev-lead@tkt`): 만든 파일, 테스트 결과 마지막 줄, 계약에 없는 응답을 만든 곳(있으면), 스스로 정한 기술 결정(도구·구조)과 이유 한 줄씩.
3. 보고하고 멈춘다.
