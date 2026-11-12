# T-05 (server) 리뷰 #1 수정: 만료 판단을 잠금 뒤 시각으로 — GREEN

## 배경
T-03 리뷰 #1(높음): 확정(그리고 홀드)이 시각을 `Depends(get_now)`로 받아 좌석 잠금 **전에** 읽는다. 잠금 대기 중 만료된 홀드가 SOLD가 될 수 있다.
test가 T-04에서 재현 테스트를 썼고(RED), 해시를 기록했다.

## 할 일 (`docs/tasks/api-harness.md` 2·3절이 바뀌었다. 그대로 따른다)
1. 홀드·확정에서 `Depends(get_now)`를 없애고, 좌석 행을 잠근 **뒤** `clock.get_now()`를 한 번 부른다(`from backend import clock`, 모듈 경유 호출).
2. `backend.seed.lock_seat(database_url, performance_id, seat_id)` 컨텍스트 매니저를 만든다. 별도 연결에서 서버와 같은 방식(FOR UPDATE)으로 그 좌석 행을 잠그고 `with`가 끝나면 놓는다.
3. 테스트 파일은 고치지 않는다.

## 완료 기준
- `uv run pytest` 전체 통과, `uv run python scripts/story_report.py` 실패 0.
- lead에게 보고: 바꾼 파일, 결과 마지막 줄, 기술 결정 한 줄씩. 보고하고 멈춘다.
