# 동시성 확인

목표: 같은 좌석에 여러 명이 동시에 몰려도 정확히 한 명만 성공하고, 서버 오류(5xx)는 없다. 이것을 실제 서버와 PostgreSQL로 돌려 확인한다.

## 1. 테스트

`tests/concurrency/test_concurrency.py`. 테스트가 `uvicorn backend.main:app --workers 4`를 별도 프로세스로 띄우고, 테스트 DB(`tkt_test`)를 쓴다. 요청은 미리 만들어 두고 한꺼번에 출발시킨다(httpx AsyncClient).

| 테스트 | 요청 | 기대 |
|---|---|---|
| `test_concurrent_hold_500_users_one_seat` | 서로 다른 사용자 500명이 같은 좌석을 동시에 홀드 | 201 1건, 409 `SEAT_ALREADY_HELD` 499건, 5xx 0건 |
| `test_concurrent_confirm_20_same_hold` | `u1`이 같은 hold_id로 동시에 확정 20번 | 200 1건, 409 19건, 5xx 0건, `bookings`의 그 좌석 줄 1개 |

- 확정의 성공 코드는 계약(`docs/openapi.yaml`)의 200이다.
- 한 번 통과는 운일 수 있어서, `uv run pytest tests/concurrency`를 3번 연속 돌려 모두 통과해야 통과로 본다.

## 2. 찾은 결함: DB 연결 한도

처음 실행에서 홀드 500건 테스트가 실패했다. 성공(201)은 매번 1건이었지만 `500 INTERNAL_ERROR`가 148~261건 나왔다.

- 원인: `psycopg.OperationalError: FATAL: sorry, too many clients already`. 워커 4개 × 연결 풀(`pool_size` 10 + `max_overflow` 20 = 30) = 최대 120 연결이 PostgreSQL `max_connections` 100을 넘었다.
- 수정(`backend/db.py`): 워커당 연결 풀을 `pool_size` 10 + `max_overflow` 5 = 15로 줄였다. 4 × 15 = 60이라 한도 안이고, 남는 40은 테스트·마이그레이션 여유다. 한도를 넘는 요청은 풀에서 연결을 기다린다(`pool_timeout` 30초).
- 주의: 전체 연결 수는 `서버 인스턴스 수 × 워커 수 × 15`다. 인스턴스나 워커를 늘리면 이 값이 `max_connections` 이하인지 다시 맞춰야 한다(T-18 리뷰 #2).
- 다루지 않은 경우: 연결 15개가 모두 잠금 대기에 묶여 다음 요청이 `pool_timeout`(30초)을 넘기면 지금은 `500 INTERNAL_ERROR`가 된다. 과부하 때 어떤 응답(예: 503)을 줄지는 계약 결정이 필요하다(PRD 열린 질문 Q15).

## 3. 테스트가 겹침을 잡는지 확인 (잠금 제거 실험)

`lock_seat`의 `with_for_update()`를 잠깐 빼고 돌렸다(되돌린 뒤 흔적 없음 확인).

| 테스트 | 잠금 없음 | 잠금 있음 |
|---|---|---|
| 홀드 500건 | **FAIL**: 201 4건, 409 496건 (이중 홀드) | PASS |
| 확정 20건 | **FAIL**: 200 1건, 500 19건 (`uq_bookings_seat` UNIQUE 위반) | PASS |

잠금이 없으면 테스트가 실제로 실패한다. 확정 쪽은 UNIQUE 제약이 이중 판매를 막았지만, 그 대가로 5xx가 났다.

## 4. 홀드 방식 비교

| 방식 | p50(ms) | p95(ms) | 201 | 409 | 5xx | 기존 테스트 |
|---|---:|---:|---:|---:|---:|---|
| A. `SELECT … FOR UPDATE`로 좌석 행을 잠그고 판단·변경 (현재) | 310 | 418 | 1 | 499 | 0 | 전체 통과 |
| B. 조건부 `UPDATE … WHERE (홀드 가능) RETURNING` 한 번 | 342 | 374 | 1 | 499 | 0 | **1건 실패** |

- 측정: 좌석 1석에 서로 다른 사용자 500명이 동시에 홀드, 라운드마다 데이터 초기화. 워밍업 1회를 빼고 10라운드를 재서 중앙값을 적었다. 201·409·5xx 수는 매 라운드 같았다.
- 라운드별 범위: A p50 288~336, p95 375~449 / B p50 309~357, p95 344~399. 두 방식의 범위가 겹친다. 응답 시간 대부분은 HTTP와 연결 풀 대기 시간이다.
- B는 저장소 복사본에서만 만들어 쟀고, 저장소에는 넣지 않았다.

### 측정 환경
| 항목 | 값 |
|---|---|
| 기기 | Apple M4, 10코어, 메모리 24GiB |
| OS | macOS 27.0.1 |
| Python | 3.12.16 |
| PostgreSQL | 16.15 (docker `postgres:16-alpine`, 같은 기기) |
| 서버 | uvicorn 워커 4개 |
| DB 연결 풀 | 워커당 `pool_size` 10 + `max_overflow` 5 |
| 클라이언트 | httpx asyncio, 동시 요청 500건 한꺼번에 출발, `max_connections` 600 |
| 측정 DB | `tkt_test` (DB 분리 전). 이후 벤치마크는 `tkt_server`에서 돌린다(`docs/tasks/api-harness.md` 4절) |

### 남긴 방식: A (FOR UPDATE)
1. **정확성.** B는 기존 테스트 `test_us03_ac03_3_expiry_judged_after_seat_lock`에서 실패했다. B는 시각을 UPDATE 전에 읽어야 해서, 행 잠금을 기다리는 동안 지난 시간이 만료 판단에 들어가지 않는다(T-03 리뷰 #1, `docs/tasks/api-harness.md` 2절).
2. **단순함.** B를 정확하게 만들려면 만료 시각을 `seats` 행에 복사하는 컬럼과 마이그레이션이 필요하다. 만료 시각을 `holds`에서 하위 질의로 읽으면, PostgreSQL READ COMMITTED에서 막혔던 행을 다시 확인할 때 다른 트랜잭션이 막 넣은 홀드 행이 보이지 않아 이중 홀드가 될 수 있다.
3. **속도.** 차이가 작고 범위가 겹친다. B가 빠르다고 할 근거가 없다.

## 5. 예매 표 UNIQUE 제약

`bookings`에는 처음 마이그레이션(`backend/migrations/versions/0001_initial.py`)부터 `uq_bookings_seat` UNIQUE (performance_id, seat_id)가 있다. 테스트 DB에서 `\d bookings`로 확인했다. 새 마이그레이션은 만들지 않았다.

## 6. 리뷰(T-18) 결과와 처리

review 결론: 홀드와 확정은 좌석 행 하나를 FOR UPDATE로 같은 순서로 잠그고, 시각도 잠금 뒤에 한 번 읽는다. 이중 판매나 좌석 사이 교착 경로는 찾지 못했다. 이 문서의 A·B 설명은 코드와 맞는다.

| 번호 | 심각도 | 지적 | 처리 |
|---|---|---|---|
| 1 | 중간 | 좌석맵이 좌석과 홀드를 서로 다른 SQL 문으로 잠금 없이 읽어, 그 사이 확정·재홀드가 커밋되면 이전 상태를 보일 수 있다 | **바꾸지 않음.** 홀드 행은 만들어진 뒤 바뀌지 않으므로, 응답은 좌석을 읽은 순간의 상태와 같다. 응답이 나간 직후 상태가 바뀌는 것과 같은 정도의 지연이고, 한 응답 안에서 서로 맞지 않는 상태가 섞이지는 않는다. 판매 판단은 좌석맵이 아니라 잠금을 잡은 홀드·확정이 한다 |
| 2 | 중간 | 연결 한도 식이 인스턴스 수를 빠뜨림. 풀 대기가 30초를 넘으면 500 | 식을 고침(2절, `backend/db.py` 주석). 과부하 응답은 PRD Q15로 올림 |
| 3 | 낮음 | 실제 서버 테스트가 다루지 않는 경쟁: 만료 경계에서 이전 홀드 확정과 재홀드, 다른 사용자의 같은 hold_id 동시 확정, 좌석맵과 상태 변경 | **이번에 테스트 추가 안 함.** 다른 사용자의 확정은 응답이 열린 질문 Q3이다. 만료 경계는 실제 서버(다른 프로세스)에서 시각을 바꿀 방법이 없고 테스트 전용 경로는 만들지 않는다. 같은 판단(잠금 뒤 시각·`current_hold_id` 확인)은 `tests/api/`의 `..._expiry_judged_after_seat_lock`, `test_us04_ac04_6_hold_then_confirm_race`가 확인한다. 좌석맵은 1번과 같다 |
