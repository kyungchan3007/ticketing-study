# T-22 (server) 예매 UNIQUE 위반을 409 SEAT_ALREADY_SOLD로 — 통과(PASS)

## 배경
사람 결정: `bookings`의 `uq_bookings_seat` 위반은 서버 고장이 아니라 "이미 팔린 좌석"이므로 409 `SEAT_ALREADY_SOLD`로 응답한다. 계약은 이미 confirmBooking 409 `SEAT_ALREADY_SOLD`를 갖고 있어 바꾸지 않는다.
테스트(T-21, 해시 기록됨): `tests/api/test_unique_violation.py`. 옛 홀드와 그 bookings 줄을 DB에 직접 넣어 둔 뒤 확정하면 지금은 500이 나온다.

## 할 일
1. `backend/`만 고쳐서 확정의 `uq_bookings_seat` 위반을 409 `SEAT_ALREADY_SOLD`(`{code, message}`)로 응답한다.
2. **이 UNIQUE 위반만** 409로 바꾼다. 다른 IntegrityError(다른 제약 위반)나 다른 DB 오류는 지금처럼 처리하지 못한 예외 → 500 `INTERNAL_ERROR`로 둔다. 제약 이름이나 오류 종류로 골라낸다.
3. 위반이 난 트랜잭션은 롤백되어 bookings와 좌석 상태가 바뀌지 않아야 한다. 위반 뒤에도 서버가 정상 동작해야 한다.
4. 테스트는 고치지 않는다.

## 완료 기준
- `uv run pytest` 전체 통과, `uv run pytest tests/concurrency` 통과.
- lead에게 보고: 바꾼 파일과 줄, 위반만 골라내는 방법, 테스트 결과 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
