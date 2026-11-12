# 기술 결정 기록

한 줄에 하나씩, 이유와 함께 적는다. 누가 정했는지 괄호로 표시한다.

- 2026-11-12 (lead) 런타임 의존성 fastapi, uvicorn, sqlalchemy, alembic, psycopg[binary], 개발 의존성 httpx — 스택 결정(FastAPI+PostgreSQL)과 마이그레이션 요구를 가장 흔한 도구로 채우고, psycopg는 3판이 SQLAlchemy 2와 바로 맞고 binary 판은 로컬 libpq 설치가 필요 없어서.
- 2026-11-12 (lead) 시각은 `backend.clock.get_now`를 FastAPI 의존성으로 받고 테스트는 `dependency_overrides`로 바꿔 끼운다 — 테스트 전용 HTTP 경로 없이 시각을 고정할 수 있는 FastAPI 기본 방식이라서.
- 2026-11-12 (lead) 테스트 데이터는 HTTP가 아니라 파이썬 함수 `backend.seed.reset`으로 넣는다 — 등록 API와 테스트 전용 경로를 만들지 않기로 했으므로.
- 2026-11-12 (lead) 테스트 DB는 개발 DB(`tkt`)와 분리한 `tkt_test` — 테스트가 데이터를 지워도 개발용 시드가 남게 하려고.
- 2026-11-12 (lead) DB에 연결할 수 없으면 API 테스트는 건너뛰지 않고 실패한다 — 건너뛰면 통과표가 초록으로 보여 RED/GREEN 판단이 흐려지므로.
- 2026-11-12 (lead) 테스트와 서버의 파이썬 접점은 `docs/tasks/api-harness.md` 한 곳에 정한다 — test와 server가 따로 일하면서도 같은 함수 이름을 쓰게 하려고.
- 2026-11-12 (lead) `scripts/story_report.py` 기본 대상을 tests/contract와 tests/api 둘 다로 넓힘 — 인자 없이 돌려도 계약 테스트와 API 테스트를 함께 세도록.
- 2026-11-12 (test) API 테스트의 경로·성공 코드는 openapi.yaml을 operationId로 읽어 쓴다 — 계약이 바뀌면 테스트가 따라가게.
- 2026-11-12 (test) 응답 본문은 jsonschema로 openapi.yaml components 스키마에 검증한다. (lead) jsonschema를 직접 개발 의존성으로 올림 — 다른 도구의 하위 의존성에 기대면 그 도구가 바뀔 때 깨지므로.
- 2026-11-12 (test) 동시성 테스트는 스레드 10개 + Barrier, 스레드마다 별도 TestClient, 같은 테스트 안에서 3회 반복 — 한 번의 운으로 통과하는 것을 줄이려고.
- 2026-11-12 (test) backend가 없거나 DB에 연결할 수 없으면 pytest.fail(건너뛰기 없음) — 접점 문서의 '실패' 규칙대로.
- 2026-11-12 (server) PostgreSQL은 docker-compose의 postgres:16-alpine, 헬스체크 포함, 초기화 SQL로 tkt_test 생성 — 누구나 같은 DB를 한 명령으로 띄우게.
- 2026-11-12 (server) 홀드·확정은 좌석 행을 SELECT ... FOR UPDATE로 잠근 뒤 같은 트랜잭션에서 판단과 변경, bookings에 (공연, 좌석) UNIQUE 안전망 — 동시 요청을 좌석 단위로 직렬화하고 두 번 팔림을 DB가 한 번 더 막게.
- 2026-11-12 (server) 만료는 읽는 시점에 now >= expires_at으로 계산하고 청소 작업은 없음 — 시각 주입만으로 검증되고 경계값 판단이 한 곳에 있게.
- 2026-11-12 (server) 확정 판정 순서: 없는 홀드 404 → SOLD 409 → 남의 홀드 403 → 대체·만료 409 HOLD_EXPIRED — AC-04-4가 SOLD 좌석이면 SEAT_ALREADY_SOLD를 요구해서 SOLD를 소유자 확인보다 앞에 둠.
- 2026-11-12 (server) 트랜잭션은 핸들러 안의 with Session/session.begin()으로 닫음 — yield 의존성은 응답 뒤에 정리돼 잠금이 늦게 풀릴 수 있어서.
- 2026-11-12 (server) alembic.ini 없이 db.migrate()가 Alembic 설정을 코드로 만들고, env.py에서 pg_advisory_lock으로 동시 migrate를 직렬화 — 루트 설정 파일을 늘리지 않으려고.
- 2026-11-12 (server) seed.reset은 TRUNCATE 대신 자식 테이블부터 DELETE — 열린 앱 연결과의 잠금 대기를 피하려고.
- 2026-11-12 (server) 계약에 없는 오류: 남의 홀드 확정 403 FORBIDDEN(Q3), 없는 hold_id 404 NOT_FOUND(Q4), 요청 형식 오류 400 VALIDATION_ERROR(Q9), 없는 경로 404·405 — 모두 {code, message} 형식. 열린 질문의 임시 처리이며 계약 enum에는 아직 없음.
- 2026-11-12 (lead) 시각 접점 변경: Depends(get_now)·dependency_overrides 대신 서버가 잠금 뒤 clock.get_now()를 부르고 테스트는 monkeypatch로 바꿔 끼움 — 의존성은 잠금 전에 풀려 만료 판단이 잠금 대기 전 시각으로 됐기 때문(T-03 리뷰 #1).
- 2026-11-12 (lead) 잠금 대기 재현용 backend.seed.lock_seat 추가 — 테스트 전용 HTTP 경로 없이 잠금 경쟁을 결정적으로 재현하려고.
- 2026-11-12 (test) 잠금 대기 재현은 pg_stat_activity에서 wait_event_type='Lock'을 확인한 뒤 시각을 바꿈 — sleep 추측이 아니라 실제 대기를 확인하려고.
- 2026-11-12 (server) 좌석맵도 Depends(get_now)를 없애고 핸들러 안에서 clock.get_now() 호출 — Depends는 함수 객체를 붙잡아 monkeypatch가 먹지 않으므로.
- 2026-11-12 (server) lock_seat는 별도 엔진에서 서버와 같은 select(Seat)...with_for_update()로 잠그고 롤백으로 놓음 — 서버와 같은 잠금이어야 대기 재현이 의미 있으므로.
