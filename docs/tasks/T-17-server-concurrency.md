# T-17 (server) 동시성: 잠금 제거 실험, 홀드 방식 비교, 한 방식만 남기기

## 배경
- 테스트(T-16, 해시 기록됨, 12개 파일): `tests/concurrency/`. 실제 uvicorn 워커 4개와 PostgreSQL로 동시 홀드 500건, 같은 홀드 동시 확정 20건을 확인한다.
- lead가 `uv run pytest tests/concurrency`를 3번 연속 돌려 모두 통과해야 통과로 본다.

## 할 일
### 0. 먼저: 동시 홀드 500건의 5xx (T-16에서 발견, 지금 FAIL)
- 지금 서버로 `uv run pytest tests/concurrency`를 돌리면 홀드 500건 테스트가 실패한다. 201은 항상 1건이지만 `500 INTERNAL_ERROR`가 148~261건 나온다.
- 서버 로그 원인: `psycopg.OperationalError: FATAL: sorry, too many clients already`. PostgreSQL `max_connections`=100인데, 워커 4개 × 연결 풀(`pool_size` 10 + `max_overflow` 20 = 30) = 최대 120 연결이다.
- 몰려도 DB 연결 한도를 넘지 않게 고친다. 방법은 server가 정하고 이유를 보고한다. 테스트 기대값(5xx 0건)은 바꾸지 않는다.
- 이 수정이 끝난 뒤에 1번 실험을 한다(5xx와 섞이면 판단이 흐려진다).

### 1. 테스트가 겹침을 잡는지 확인 (잠금 제거 실험)
- `backend/main.py`의 `lock_seat`에서 `with_for_update()`를 잠깐 빼고 `uv run pytest tests/concurrency`를 돌려 **실패(FAIL)** 하는지 본다. 실패 출력(응답 코드별 개수)을 기록한다.
- 원래대로 되돌린다. `git diff backend/`로 실험 흔적이 없는지 확인한다.

### 2. 홀드 방식 두 가지 비교
- A: 지금의 FOR UPDATE 방식.
- B: 조건부 UPDATE 한 번으로 끝내는 방식(UPDATE … WHERE 홀드 가능 조건 … RETURNING).
- 같은 조건(같은 서버 실행 방식, 같은 좌석 1석에 서로 다른 사용자 500건 동시 홀드)에서 각각 재서 p50, p95(ms), 201·409·5xx 수를 얻는다. 한 번만 재지 말고 여러 번 재서 대표값을 정한다(몇 번 쟀는지 적는다).
- 측정 환경을 적는다: 기기·CPU·메모리, OS, Python·PostgreSQL 버전, uvicorn 워커 수, DB 연결 풀 설정, 클라이언트 동시 연결 수.
- 측정 스크립트는 저장소 밖(예: 자기 임시 폴더)에 두고, 실행 명령을 보고에 적는다.

### 3. 하나만 남기기
- 더 단순하고 빠른 쪽 하나만 남기고 비교용 코드는 지운다.
- 남기는 방식은 **기존 테스트를 모두 통과해야 한다.** 특히:
  - 시각은 좌석 잠금(또는 그 행을 바꾸는 순간) 뒤에 읽은 값으로 만료를 판단한다(`docs/tasks/api-harness.md` 2절, T-03 리뷰 #1). `tests/api/`의 `..._expiry_judged_after_seat_lock` 테스트가 이것을 확인한다.
  - B를 쓴다면, 다른 트랜잭션이 막 바꾼 좌석 행을 다시 확인할 때 WHERE 조건 안의 하위 질의(예: holds 테이블의 만료 시각)가 최신 값을 보는지 확인한다. PostgreSQL READ COMMITTED에서는 다시 확인하는 대상이 바뀐 행 자체뿐이다.
- 빠르지만 정확하지 않으면 남기지 않는다. 정확성이 먼저다.

### 4. 예매 표 UNIQUE 제약
- `bookings`에는 이미 `uq_bookings_seat`(performance_id, seat_id) UNIQUE 제약이 있다(`backend/migrations/versions/0001_initial.py`). 실제 테스트 DB에 걸려 있는지 확인하고(예: `\d bookings`), 있으면 새 마이그레이션은 만들지 않는다. 없으면 마이그레이션으로 추가한다.

### 5. 제한
- `backend/`만 수정한다. 테스트는 고치지 않는다. `docs/`는 lead가 쓴다(측정값은 보고로 보낸다).
- 여러 좌석 동시 홀드, Redis·대기열은 하지 않는다.

## 완료 기준
- `uv run pytest tests/concurrency` 통과, `uv run pytest` 전체 통과.
- lead에게 보고:
  0. 5xx 원인 수정 내용과 이유(바꾼 설정·줄).
  1. 잠금 제거 실험 결과(실패 출력)와 되돌림 확인.
  2. 비교표(방식, p50, p95, 201, 409, 5xx, 측정 횟수)와 측정 환경, 측정 명령.
  3. 남긴 방식과 이유, 바꾼 파일과 줄.
  4. UNIQUE 제약 확인 결과.
- 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
