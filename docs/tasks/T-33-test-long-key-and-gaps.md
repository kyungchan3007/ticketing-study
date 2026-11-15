# T-33 (test) 긴 Idempotency-Key 500 결함과 빠진 확인 세 가지 — 실패(FAIL)

## 배경
- 사람이 셸에서 재현한 결함: 무작위 3000자 키로 예매 요청 → 500 `INTERNAL_ERROR`. 로그 `index row size 3016 exceeds btree version 4 maximum 2704 for index "uq_bookings_user_key"`.
- lead 결정(계약 반영): `Idempotency-Key`는 1~255자. 255자를 넘으면 400 `VALIDATION_ERROR`(`docs/openapi.yaml` IdempotencyKey `maxLength: 255`, PRD 3·5절, US-04 AC-04-14).

## 할 일
1. **결함 테스트(FAIL이어야 함):** US-04 AC-04-14. 256자 키와 3000자 키 → 400 `VALIDATION_ERROR`, 예매 줄 0개. 255자 키 → 2xx `PENDING`(경계). 지금 서버에서 256·3000자는 실패해야 한다. 실패 이유가 "500 INTERNAL_ERROR"(또는 256자는 2xx)인지 확인한다. 이름 `test_us04_ac04_14_...`.
2. **빠진 확인(지금 서버에서 PASS여도 된다, 회귀 방지):**
   - US-05 AC-05-7 확장: `tests/concurrency`에서 실제 서버로, 좌석 여러 개(예: 5석)에 각각 홀드·예매 요청을 만든 뒤 좌석마다 같은 성공 콜백 여러 건(예: 좌석당 10건)을 한꺼번에 동시에 보낸다. 좌석마다 `PAID` 1개·SOLD, 모든 응답 2xx·`PAID`, 5xx 0건.
   - US-04 AC-04-15: `u1`·`u2`가 같은 키 `k1`로 각자의 홀드에 예매 요청 → 둘 다 2xx, `booking_id` 다름, 사용자·좌석이 자기 것. 같은 키로 다시 보내면 각자 자기 예매. (원하면 동시 출발도 넣는다.)
   - US-05 AC-05-4 확장: 실패 콜백 뒤 새 키로 다시 요청하면, 그 좌석의 예매가 `FAILED` 1개와 `PENDING` 1개다(DB에서 확인).
3. 바뀌지 않은 테스트의 기대값은 그대로 둔다. `tests/`만 수정한다. 커밋하지 않는다.

## 보고
CLAUDE.md 보고 형식 표(테스트 / 결과 / 상태 코드 분포 / 소요 시간), 바꾼 파일, FAIL 이유, 지금도 통과하는 새 테스트. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. lead가 해시를 기록한다.
