# T-04 (test) 리뷰 #1 재현 테스트와 시각 접점 변경 — RED

## 배경
T-03 리뷰 #1(높음): 확정 요청이 시각을 좌석 잠금 **전에** 읽는다. 잠금을 기다리는 사이 만료 시각을 지난 홀드도 SOLD가 된다. PRD 3절 "확정은 만료 전에만"을 어긴다.
재현(리뷰): T0 홀드 → 외부 트랜잭션이 A1 행을 FOR UPDATE로 잠금 → 확정 요청이 T0+4:59를 읽고 대기 → 시각을 T0+5:00으로 바꾸고 잠금 해제 → 기대 409 HOLD_EXPIRED, 실제 200·SOLD.

## 접점 변경(`docs/tasks/api-harness.md` 2·3절, 이미 갱신됨)
- 시각은 `dependency_overrides`가 아니라 `monkeypatch.setattr(backend.clock, "get_now", ...)`로 바꿔 끼운다. 서버는 잠금 뒤에 `clock.get_now()`를 부른다.
- 잠금 대기 재현용 `backend.seed.lock_seat(database_url, performance_id, seat_id)` 컨텍스트 매니저를 쓴다(서버가 T-05에서 만든다).

## 할 일
1. `tests/api/`의 시각 주입을 새 접점(monkeypatch)으로 바꾼다. 기존 인수 조건과 기대값은 바꾸지 않는다.
2. 재현 테스트를 추가한다. 이름은 `test_us04_ac04_2_...`(US-04 / AC-04-2 경계, 리뷰 #1). 위 재현 절차대로: 확정 요청을 스레드로 보내 `lock_seat`에 막히게 한 뒤 시각을 T0+5:00으로 바꾸고 잠금을 풀어 409 `HOLD_EXPIRED`와 좌석맵 `A1` ≠ `SOLD`를 확인한다. 확정 요청이 실제로 잠금에 막혔는지(잠금을 풀기 전에 응답이 오지 않았는지)도 확인한다.
3. 같은 방식으로 홀드도 확인한다: `u1` T0 홀드 → `lock_seat` 중 `u2` 홀드가 T0+4:59를 읽고 대기 → 시각 T0+5:00 → 해제 → 기대 2xx(만료 판단이 잠금 뒤 시각). 이름 `test_us03_ac03_3_...`.
4. `tests/`만 수정한다.

## 완료 기준
- `uv run pytest tests/api`에서 새 테스트가 실패(RED)한다(`lock_seat` 없음 또는 200 응답). 실패 이유를 확인한다.
- lead에게 보고: 바꾼 파일, 새 테스트 이름, RED 출력과 이유, 기술 결정 한 줄씩. 보고하고 멈춘다.
