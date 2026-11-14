# T-23 (review) 예매 UNIQUE 위반 → 409 SEAT_ALREADY_SOLD 검토

읽기만 한다. 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다). 재현이 필요하면 재현 명령과 기대 결과를 적는다.

## 반영 내용
- 사람 결정: `bookings`의 `uq_bookings_seat` 위반은 "이미 팔린 좌석"이므로 500 대신 409 `SEAT_ALREADY_SOLD`. 계약은 그대로(confirmBooking 409 `SEAT_ALREADY_SOLD`가 이미 있음).
- 테스트(T-21): `tests/api/test_unique_violation.py`. 옛 홀드와 그 bookings 줄을 DB에 직접 넣은 뒤 확정 → 409, bookings 1줄 유지. 보조 테스트로 위반 뒤 서버 정상 동작.
- 구현(T-22): `backend/main.py`의 `is_unique_booking_violation`, 확정 핸들러의 `session.flush()` + `IntegrityError` 처리.

## 확인할 것
1. UNIQUE 위반만 409가 되는가: SQLSTATE 23505 + 제약 이름 `uq_bookings_seat`일 때만인가. 다른 제약 위반·다른 DB 오류는 500 `INTERNAL_ERROR`로 남는가(이 경로는 테스트가 없다고 server가 보고함).
2. 위반 뒤 트랜잭션이 롤백되어 좌석 상태·bookings가 바뀌지 않는가. 연결이 깨진 상태로 풀에 돌아가지 않는가.
3. 테스트가 의미 있는가: 수정 전에는 실패했는가(T-21에서 500으로 FAIL 확인), DB 직접 조작 재현이 다른 테스트와 섞이지 않는가.
4. 동시성 관점: 잠금이 있는 지금 경로에서 이 처리가 다른 동작(확정 응답 순서, 이중 판매 방지)을 바꾸지 않는가.

## 보고
번호, 심각도(높음·중간·낮음), 내용, 근거(파일:줄), 재현 방법(명령과 기대 결과)을 표로. 판정(해결/미해결). 끝에 `정한 것: ...`, `원칙 충돌: ...`.
