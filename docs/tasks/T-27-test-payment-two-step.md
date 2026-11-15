# T-27 (test) 홀드 만료와 모의 결제 두 단계 — 실패(FAIL)

## 목표
"시간 경계와 결제 두 단계를 거쳐도 좌석은 한 번만 팔리고 돈은 한 번만 반영된다"를 테스트로 고정한다. 지금 서버에는 이 기능이 없으므로, 새 테스트는 **기능이 없어서** 실패(FAIL)해야 한다.

## 먼저 읽을 것 (lead가 고쳐 둠)
- `docs/PRD.md` 1·2·3절(예매 상태 표 포함)·5절(오류 표)·10절(Q1·Q2·Q3·Q4·Q11·Q13 결정)
- `docs/stories/US-03-hold-seat.md` (AC-03-8 추가, AC-03-4 준비 문구 변경)
- `docs/stories/US-04-confirm-booking.md` (전체 다시 씀: 예매 요청 = 결제 대기)
- `docs/stories/US-05-payment-callback.md` (새 스토리)
- `docs/stories/US-02-seat-map.md` AC-02-2 준비 문구(SOLD는 성공 콜백으로)
- `docs/openapi.yaml`: `confirmBooking`(Idempotency-Key 헤더, 응답 `Booking`, 400·403·404·409), 새 `paymentCallback`(`POST /payments/{booking_id}/callback`, 본문 `PaymentCallback`), `Error` enum 추가분
- `docs/tasks/api-harness.md` 6절: 테스트가 DB를 직접 볼 때 기대어도 되는 표·열·제약 이름

## 할 일
### 1. 바뀐 요구에 맞춰 기존 테스트 고치기
요구가 바뀌어서 기대값이 달라지는 테스트만 고친다. 바뀌지 않은 인수 조건의 기대값은 그대로 둔다.
- "확정하면 SOLD"를 쓰던 곳은 "예매 요청 → 성공 콜백 → SOLD"로 바꾼다(US-02 AC-02-2, US-03 AC-03-4, US-04 전부, 계약 테스트).
- US-04 AC-04-8은 403 `FORBIDDEN`, AC-04-9는 404 `NOT_FOUND`로 정확히 확인한다(이제 결정됨).
- `tests/contract/test_openapi.py`: `Confirmation` 대신 `Booking`, 새 `paymentCallback`, enum 추가분.
- `tests/concurrency`의 같은 홀드 동시 확정 20건: Q1·Q13 결정에 따라 "20건 모두 성공, `booking_id` 모두 같음, 그 홀드의 활성 예매 1줄, 5xx 0건"으로 바꾼다.
- `tests/api/test_unique_violation.py`: 확정은 이제 `PAID` 줄을 만들지 않으므로 `uq_bookings_seat` 위반은 **성공 콜백**에서만 생긴다. 사람이 앞서 정한 뜻("UNIQUE 위반은 서버 고장이 아니라 이미 팔린 좌석")을 두 단계에 맞춰 옮긴다: 위반이 나면 그 콜백은 2xx이고, 예매는 `REFUND_REQUIRED`, 좌석은 바뀌지 않는다. 다른 IntegrityError는 지금처럼 500 `INTERNAL_ERROR`. 재현 방법은 test가 정한다(테스트 전용 HTTP 경로 금지, `backend/` 수정 금지).

### 2. 새 테스트
- US-03 AC-03-8, US-04 AC-04-1·2·5·10·11·12·13(새로 생기거나 바뀐 것), US-05 AC-05-1 ~ AC-05-9.
- **경계 시각:** 홀드 `T0` 기준 4분 59초·5분 정각·5분 1초를 예매 요청(US-04 AC-04-1·2)과 성공 콜백(US-05 AC-05-1·2) 양쪽에서 확인한다.
- **잠금 뒤 시각:** 성공 콜백이 T0+4분59초를 읽고 좌석 잠금에서 기다리는 사이 T0+5분이 되면 `REFUND_REQUIRED`(기존 `..._expiry_judged_after_seat_lock`과 같은 방식, `env.blocked_by_seat_lock`). PRD "시각은 서버 시각만, 잠금 뒤에 읽는다"를 지키는지 본다.
- **동시 중복 콜백(AC-05-7):** `tests/concurrency`에 5장처럼 실제 서버(`uvicorn --workers 4`)·PostgreSQL·실제 시계로. 같은 예매의 성공 콜백 20건을 동시에 출발시킨다. 기대: 20건 모두 2xx·`PAID`, 5xx 0건, 좌석 SOLD, 그 좌석의 `PAID` 줄 1개. lead가 3번 연속 돌린다.
- **이름:** 모든 스토리 테스트는 `test_us<NN>_ac<NN>_<M>_...`로 시작하고 docstring 첫 줄에 `US-05 / AC-05-1: ...`처럼 스토리·인수 조건을 적는다. `scripts/story_report.py`가 `docs/stories`에서 US-05 줄을 만들고, 기본 대상에 `tests/concurrency`도 넣었다.
- 요청 헬퍼(`Idempotency-Key` 헤더, 콜백 본문)는 `tests/api/conftest.py`에 더해도 된다. 경로·성공 코드는 지금처럼 계약에서 operationId로 읽는다.

### 3. 실패 이유 확인
- `uv run pytest`를 돌려, 새 테스트·고친 테스트가 **기능이 없어서** 실패하는지 하나씩 확인한다(예: 콜백 경로 404, 응답에 `booking_id`·`status` 없음, 확정이 바로 SOLD로 만듦, 400·403 대신 다른 코드). 준비 코드 오류(픽스처·이름 오류, DB 연결 실패)로 실패하는 것이 없어야 한다.
- 지금 서버에서도 통과하는 새 테스트가 있으면 이름과 이유를 적는다(예: 본인 재홀드 409는 지금도 그렇다).
- 바뀌지 않은 기존 테스트는 계속 통과해야 한다.

## 제한
- `tests/`만 수정한다. 서버(`backend/`)·문서는 고치지 않는다. 문서가 모호하거나 틀리면 lead에게 알린다.
- 실제 환불, 대사, 서버 여러 대는 하지 않는다. 커밋하지 않는다.

## 보고
- CLAUDE.md 보고 형식 표: 테스트 / 결과(FAIL·PASS) / 상태 코드 분포 / 소요 시간(전체, p95). 테스트가 많으면 스토리별로 묶고, FAIL 이유를 "실패 이유" 칸에 짧게 적는다.
- 바꾼 파일, 고친 기존 테스트와 이유, UNIQUE 위반 재현 방법, 지금도 통과하는 새 테스트.
- 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. lead가 해시를 기록한다.
