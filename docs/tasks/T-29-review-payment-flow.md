# T-29 (review) 결제 흐름 검토 — 홀드 만료와 모의 결제 두 단계

읽기만 한다. 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다). 재현이 필요하면 재현 명령과 기대 결과를 적는다.

## 반영 내용
- 요구: `docs/PRD.md` 2·3·5·10절, `docs/stories/US-04-confirm-booking.md`, `docs/stories/US-05-payment-callback.md`, `docs/openapi.yaml`, `docs/tasks/api-harness.md` 6절.
- 테스트(T-27, 해시 14개): `tests/api/test_us04_confirm_booking.py`, `tests/api/test_us05_payment_callback.py`, `tests/api/test_unique_violation.py`, `tests/concurrency/test_concurrency.py`, `tests/api/conftest.py`, `tests/contract/test_openapi.py`.
- 구현(T-28): `backend/migrations/versions/0002_payment_two_step.py`, `backend/models.py`, `backend/main.py`(`confirm_booking`, `payment_callback`).
- 결과(lead 확인): 116 passed, concurrency 3번 연속 통과, story_report US-05 20 통과·실패 0, 마이그레이션 0002 → 0001 → 0002 확인.

## 확인할 것
1. **돈은 한 번만:** 같은 키 재요청, 다른 키 동시 요청, 같은 콜백 중복·동시, 끝난 예매에 반대 결과 콜백에서 예매·PAID가 둘이 될 길이 있는가. 같은 키를 서로 다른 좌석에 동시에 쓰는 경우(잠금이 달라 제약에 기대는 곳)는 맞게 처리되는가.
2. **좌석은 한 번만:** 성공 콜백이 SOLD로 만드는 조건(만료 전, 현재 홀드 일치, 안 팔림)이 빠짐없는가. 늦은 콜백·대체된 홀드·이미 팔린 좌석이 모두 REFUND_REQUIRED로 가고 좌석을 바꾸지 않는가.
3. **시각:** 예매 요청·콜백 모두 좌석 잠금 뒤 `clock.get_now()` 한 번으로만 판단하는가. 결제사 시각·DB `now()`를 쓰지 않는가. 경계(4분 59초·5분·5분 1초)가 PRD "현재 시각 ≥ expires_at이면 만료"와 맞는가.
4. **판정 순서:** 예매 요청의 순서(키 → 본인 기존 예매 → SOLD → 403 → 만료)가 문서·계약과 맞는가. server가 `test_internal_error.py` 때문에 키 검사를 홀드 조회 뒤로 둔 것이 문제를 만드는가.
5. **오류 처리:** `uq_bookings_seat` 위반만 REFUND_REQUIRED, 다른 IntegrityError는 500인가. SAVEPOINT 뒤 트랜잭션·연결 상태가 깨끗한가.
6. **마이그레이션:** 0002의 기존 줄 이전과 downgrade(PAID 아닌 줄 삭제)가 안전한가.
7. **테스트가 의미 있는가:** 특히 임시 인덱스(`zz_test_one_paid_per_performance`)로 "다른 제약은 500"을 지키는 방식, 동시 콜백 테스트가 정말 겹치는가.

## 보고
번호, 심각도(높음·중간·낮음), 내용, 근거(파일:줄), 재현 방법(명령과 기대 결과). 판정(해결/미해결). 끝에 `정한 것: ...`, `원칙 충돌: ...`.
