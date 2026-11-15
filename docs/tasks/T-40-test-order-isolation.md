# T-40 (test) 테스트 격리 — 순서를 바꿔 돌리기

## 배경
review(T-39)가 코드를 읽었고, 보통의 순차 실행에서는 순서에 따라 결과가 달라지는 테스트를 찾지 못했다. 근거는 다음과 같다.
- `env` fixture가 테스트마다 시작 전에 bookings → holds → seats → performances를 지우고 시드를 다시 넣는다.
- concurrency도 테스트마다 reset한다.
- 임시 인덱스는 finally에서 지운다.

낮음 지적이 1건 있다. `test_us04_ac04_13_same_key_two_seats_overlap_forced`(tests/api/test_us04_confirm_booking.py:256-259)는 요청 스레드를 `join(timeout=30)`만 하고, 스레드가 아직 살아 있는지는 검사하지 않는다. 그래서 요청이 멈추는 회귀가 생기면 다음 테스트의 reset이 기다릴 수 있다.

## 할 일
아래 순서로 돌리고 표로 보고한다. **실패가 없으면 아무것도 고치지 않는다**(낮음 지적도 그대로 둔다). 서버 코드(`backend/`)는 고치지 않는다.

1. review가 적은 순서 4개(각각 `-p no:cacheprovider`):
   - R1: `tests/api/test_us01_performance_list.py::test_us01_ac01_2_list_empty` → `tests/api/test_us04_confirm_booking.py::test_us04_ac04_1_confirm_own_hold_before_expiry`
   - R2: `tests/concurrency/test_concurrency.py::test_concurrent_hold_500_users_one_seat` → `tests/api/test_us04_confirm_booking.py::test_us04_ac04_1_confirm_own_hold_before_expiry` → `tests/concurrency/test_concurrency.py::test_concurrent_confirm_20_same_hold`
   - R3: `tests/api/test_unique_violation.py::test_other_integrity_error_stays_500_internal_error` → `tests/concurrency/test_concurrency.py::test_us05_ac05_7_concurrent_callbacks_many_seats`
   - R4: `test_us04_ac04_13_same_key_two_seats_overlap_forced` → 다른 `env` 테스트 하나
2. 동시 홀드 → API 테스트 전체 → 동시 확정: `uv run pytest <동시 홀드 노드> tests/api <동시 확정 노드> -p no:cacheprovider`
3. 전체를 무작위로 섞은 순서 3번. 플러그인을 더하지 않는다. `uv run pytest --collect-only -q`로 노드 ID를 모은 뒤, 고정 시드(예: 1, 2, 3)로 섞어서 그 순서대로 인자로 넘긴다. 스크립트는 scratch 폴더에 두고, 저장소에는 넣지 않는다. 시드와 처음 몇 개의 노드를 보고에 적는다. 넘긴 순서대로 실제로 실행됐는지 `-v` 출력으로 확인한다.

이름이 위와 다르면 실제 이름으로 바꿔서 돌리고, 바꿨다고 적는다.

## 실패가 나오면
원인을 찾는다. 테스트 쪽 공유 상태가 원인이면 `tests/` 안에서 고치고, 같은 순서로 다시 돌린다. 서버 코드가 원인이면 고치지 말고 멈춰서 lead에게 알린다. 테스트의 기대값은 바꾸지 않는다.

## 보고
표를 순서마다 한 줄씩 만든다. 열은 순서 / 통과 수 / 실패 수 / 소요 시간이다. 실패가 있었다면 원인과 고친 내용을 적는다. 끝에 `정한 것: ...`, `원칙 충돌: ...`을 적는다. 보고하고 멈춘다. 커밋하지 않는다.
