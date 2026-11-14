# T-21 (test) 예매 UNIQUE 위반을 409 SEAT_ALREADY_SOLD로 — 실패(FAIL)

## 배경
`bookings`의 `uq_bookings_seat` UNIQUE (performance_id, seat_id)는 이중 판매의 마지막 방어선이다. 지금은 위반이 생기면 처리하지 못한 예외로 `500 INTERNAL_ERROR`가 된다. 5장 잠금 제거 실험에서 확정 19건이 500이 된 이유다(`docs/concurrency.md` 3절).
사람 결정: UNIQUE 위반은 서버 고장이 아니라 "이미 팔린 좌석"이므로 **409 `SEAT_ALREADY_SOLD`** 로 응답한다. 계약(`confirmBooking` 409, code `SEAT_ALREADY_SOLD`)에 이미 있는 응답이라 계약은 바꾸지 않는다.

## 할 일
1. 확정(`confirmBooking`)이 `uq_bookings_seat` 위반을 만났을 때 409 `SEAT_ALREADY_SOLD`, `{code, message}` 형식인지 확인하는 테스트를 쓴다. 지금은 500이라 실패(FAIL)해야 한다.
   - 지금은 좌석 잠금이 있어서 실제 요청만으로는 위반이 잘 생기지 않는다. **재현 방법은 test가 정한다.** 테스트 전용 HTTP 경로는 만들지 않는다. 서버 코드(`backend/`)를 고치지 않고 재현해야 한다.
   - 위반 뒤 상태도 확인한다: 그 좌석의 `bookings` 줄은 여전히 1개다.
2. **UNIQUE 위반만** 409가 되는지 지키는 테스트도 둔다. 다른 오류(예: DB 연결 끊김)는 지금처럼 500 `INTERNAL_ERROR`여야 한다. 이미 있는 테스트가 이것을 지키면 그 이름을 보고에 적는다.
3. 기존 테스트의 인수 조건과 기대값은 바꾸지 않는다. `tests/`만 수정한다.

## 완료 기준
- 새 테스트가 지금 서버에서 실패(FAIL)하고, 기존 테스트는 그대로 통과한다.
- lead에게 보고(CLAUDE.md 보고 형식 표: 테스트 / 결과 / 상태 코드 분포 / 소요 시간): 바꾼 파일, 새 테스트 이름, 재현 방법과 그 방법을 고른 이유, FAIL 출력 마지막 줄과 이유. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
