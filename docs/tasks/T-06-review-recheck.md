# T-06 (review) 리뷰 #1 수정 재검토

T-03 지적 #1(확정·홀드가 잠금 전에 시각을 읽음)을 아래처럼 반영했다. 파일은 수정하지 말고 읽기와 테스트 실행만 한다. 데이터를 바꾸는 재현은 `tkt_test`에서만 한다(`DATABASE_URL`을 반드시 명시).

- 접점 변경: `docs/tasks/api-harness.md` 2·3절(잠금 뒤 `clock.get_now()`, 테스트는 monkeypatch, `backend.seed.lock_seat`).
- 재현 테스트(test, T-04): `tests/api/test_us04_confirm_booking.py::test_us04_ac04_2_expiry_judged_after_seat_lock`, `tests/api/test_us03_hold_seat.py::test_us03_ac03_3_expiry_judged_after_seat_lock`.
- 수정(server, T-05): `backend/main.py`, `backend/seed.py`.

## 확인할 것
1. #1이 해결됐는가: T-03의 재현 절차가 이제 409 `HOLD_EXPIRED`인가. 재현 테스트가 수정 전 코드에서는 실패하고 수정 후 통과하는 의미 있는 테스트인가.
2. 수정이 새 문제를 만들지 않았는가: 시각을 읽는 곳이 `clock.get_now()` 하나뿐인가, 잠금·트랜잭션 순서, 기존 경계값.
3. #2~#4(계약에 없는 404·403·400·405)는 열린 질문 Q3·Q4·Q9 결정 대기로 이번에 고치지 않았다. 상태만 다시 확인한다.

## 보고
T-03과 같은 표(번호, 심각도, 내용, 근거, 재현 방법)에 #1 "해결/미해결"과 새 지적을 적어 `rig send dev-lead@tkt`로 보낸다. 보고하고 멈춘다.
