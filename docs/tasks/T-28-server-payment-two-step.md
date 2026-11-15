# T-28 (server) 홀드 만료와 모의 결제 두 단계 — 구현(PASS)

## 배경
- test(T-27)가 테스트를 먼저 썼고 lead가 해시를 기록했다(14개 파일). 지금 34개가 **기능이 없어서** 실패한다(예매 응답에 `booking_id` 없음, `bookings.booking_id` 열 없음, 확정이 바로 SOLD, `Idempotency-Key` 없어도 200).
- 요구: `docs/PRD.md` 2·3·5·10절, `docs/stories/US-04-confirm-booking.md`, `docs/stories/US-05-payment-callback.md`, `docs/openapi.yaml`(`confirmBooking`, `paymentCallback`, `Booking`, `PaymentCallback`, Error enum), `docs/tasks/api-harness.md` 2절(시각)·6절(DB 사실).

## 할 일
1. **마이그레이션 0002:** api-harness 6절의 `bookings` 열과 제약(`uq_bookings_seat` 부분 UNIQUE(PAID), `uq_bookings_active_hold`, `uq_bookings_user_key`)을 만든다. 기존 `uq_bookings_seat`(전체 UNIQUE)·`hold_id` 기본 키는 바꾼다. `downgrade`로 0001로 돌아갈 수 있어야 한다.
   - 확인: `tkt_server`에서 upgrade → downgrade → upgrade를 실제로 돌리고 각 단계의 `\d bookings`(또는 같은 정보)를 보고한다. `tkt_test`는 테스트가 migrate한다.
2. **예매 요청(`confirmBooking`):** `Idempotency-Key` 필수(없으면 400 `VALIDATION_ERROR`), 결제 대기(PENDING) 예매를 만들고 좌석은 HELD 그대로. 같은 키 → 같은 예매, 다른 홀드에 같은 키 → 409 `IDEMPOTENCY_KEY_REUSED`, 그 홀드에 PENDING·PAID 예매가 있으면 그 예매를 돌려준다(만료·SOLD 뒤에도), FAILED뿐이면 만료 전에 새 예매.
   - 판정 순서(test 질문 답): 남이 산 좌석이면 403보다 409 `SEAT_ALREADY_SOLD`가 먼저다(AC-04-4, 기존 결정 "SOLD를 소유자 확인보다 앞에"). 본인의 같은 홀드 예매가 있으면 그것을 돌려주는 것이 SOLD·만료 판정보다 먼저다(AC-04-11).
3. **결제 콜백(`paymentCallback`):** `POST /payments/{booking_id}/callback`, 본문 `{"result": "SUCCEEDED"|"FAILED"}`(그 밖은 400 `VALIDATION_ERROR`, 대소문자 구분). 없는 예매 404.
   - 좌석 행을 FOR UPDATE로 잠근 **뒤에** `clock.get_now()`로 시각을 한 번 읽어 판단한다(잠금 대기 중 만료가 반영되는지 테스트가 본다).
   - 성공: 만료 전 + 좌석의 현재 홀드가 이 예매의 홀드 + 좌석이 팔리지 않음 → 좌석 SOLD, 예매 PAID. 아니면 좌석은 그대로, 예매 REFUND_REQUIRED.
   - `uq_bookings_seat` 위반(이미 다른 PAID 줄)도 "팔 수 없음"이라 2xx·REFUND_REQUIRED, 좌석은 바꾸지 않는다. 다른 IntegrityError는 지금처럼 500 `INTERNAL_ERROR`(제약 이름까지 보고 판단).
   - 실패: 예매 FAILED, 홀드 그대로. 끝난 예매에는 무엇이 와도 바꾸지 않고 지금 상태를 200으로.
4. **동시성:** 같은 예매의 성공 콜백 20건 동시(실제 서버, 워커 4개) → 모두 200·PAID, 5xx 0, PAID 줄 1개. 같은 홀드에 서로 다른 키 20개로 동시 예매 요청 → 모두 200·같은 `booking_id`. 같은 키 동시 요청도 예매 하나여야 한다. 제약 위반이 5xx로 새지 않게 한다.
5. 시각은 `backend/clock.py`만 쓴다. 결제사 시각·DB `now()`를 쓰지 않는다. DB 연결 한도 식(인스턴스 × 워커 × 15 ≤ 100)은 지킨다.

## 제한
- `backend/`만 수정한다. 테스트·문서는 고치지 않는다. 테스트가 틀려 보이면 고치지 말고 lead에게 알린다.
- 실제 환불 요청, 대사, 서버 여러 대는 하지 않는다. 커밋하지 않는다.

## 완료 기준
- `uv run pytest` 전체 통과, `uv run pytest tests/concurrency` 3번 연속 통과.
- lead에게 보고: 바꾼 파일과 핵심 줄, 마이그레이션 upgrade·downgrade 확인 결과, 판정 순서, 동시 요청을 어떻게 막았는지(잠금 대상·제약), 테스트 결과 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다.
