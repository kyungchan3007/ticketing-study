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
- 2026-11-12 (lead) [가정 G1] 접속은 오픈 1분 동안 고르게 들어옴 — 분포 자료가 없어 가장 단순한 균등 분포로 시작하고, 몰림은 실측 뒤 반영.
- 2026-11-12 (lead) [가정 G2] 한 사람은 대기열에 한 번만 진입 — 새로고침·재진입 비율 자료가 없어서.
- 2026-11-12 (lead) [가정 G3] 대기자는 모두 정확히 5초마다 폴링하고 입장하면 멈춤, 확인 시점은 사람마다 고르게 퍼져 있음 — 그래야 폴링 초당 요청을 대기 인원/5로 바로 계산할 수 있어서. 주의: 모두가 같은 순간에 확인하면 최대치가 약 5배(약 98.8만 건/초)가 될 수 있다(T-08 리뷰 #1).
- 2026-11-12 (lead) [가정 G4] 입장은 오픈 순간부터 초당 200명으로 일정 — 입장 속도는 서버가 정하는 값이라 일정하다고 보는 게 자연스러워서.
- 2026-11-12 (lead) [가정 G5] 결제 1건 = 좌석 1석, 결제 실패·홀드 만료로 풀린 좌석은 무시 — MVP가 좌석 1석·모의 결제(항상 성공 가정)라서.
- 2026-11-12 (lead) [가정 G6] 매진되면 입장을 멈추고 남은 대기자는 매진 뒤 5초 안의 다음 폴링에서 매진 안내를 받으며, 그 응답(U − N건)을 폴링 총량에 넣고 폴링 기간을 T + 5초로 함(T-08 리뷰 #2). 남은 대기자가 없으면(N = U) 매진 안내가 없으므로 기간은 T(T-10 리뷰 #4) — 팔 좌석이 없는데 입장시키면 조회·홀드 트래픽만 늘고 사용자도 헛걸음해서. 이 가정으로 입장 인원이 12.5만 명, 입장 기간이 625초로 정해진다.
- 2026-11-12 (lead) [가정 G7] 입장한 사람은 바로 조회·홀드·결제를 해서 그 요청이 입장 기간에 고르게 퍼짐 — 사람마다 머무는 시간 자료가 없어서, 입장 속도에 횟수를 곱하는 가장 단순한 모델로.
- 2026-11-12 (lead) [가정 G8] 대기열 진입·폴링은 PostgreSQL을 쓰지 않고, 조회 1회=읽기 1건, 홀드·결제 1회=쓰기 트랜잭션 1건 — 폴링 수십만 건/초는 행 잠금을 쓰는 예매 DB에 올릴 수 없는 규모라 대기열은 별도 저장소로 본다. 현재 구현의 쿼리 수와 맞는지는 실측 때 확인.
- 2026-11-12 (lead) 트래픽 시트는 평균 초당 외에 최대 초당 칸을 추가 — 폴링은 평균(약 17.8만)과 최대(약 19.8만)가 달라서, 서버 수는 최대로 정해야 하므로.
- 2026-11-12 (test) 계산 테스트는 scripts.capacity를 테스트 안에서 importlib로 불러옴 — 파일이 없을 때 수집 오류로 전체 pytest가 멈추지 않고 테스트별 FAIL이 되게.
