# T-25 (server) 회귀 방지 테스트가 실제로 잡는지 확인 (일부러 바꿨다 되돌리기)

## 배경
T-24에서 test가 회귀 방지 테스트 2개를 추가했다(지금 서버에서 PASS, 해시 기록됨). `tests/api/test_unique_violation.py`:
- `test_unique_violation_rolls_back_seat_state`: UNIQUE 위반 뒤 좌석이 HELD·u1의 홀드로 남는지.
- `test_other_integrity_error_stays_500_internal_error`: bookings 기본 키(`bookings_pkey`, 같은 SQLSTATE 23505) 위반은 500 `INTERNAL_ERROR`인지.
사람 결정: 회귀 방지용이라 지금 PASS여도 되지만, 코드를 일부러 잠깐 바꿨을 때 실패하는지 한 번 확인하고 되돌린다.

## 할 일
1. 시작 전에 `backend/main.py`를 저장소 밖 임시 폴더에 복사해 둔다.
2. 변형 A: 409로 바꾸는 조건을 모든 IntegrityError로 넓힌다(제약 이름 비교를 뺀다). `uv run pytest tests/api/test_unique_violation.py`를 돌려 `test_other_integrity_error_stays_500_internal_error`가 실패하는지 본다. 되돌린다.
3. 변형 B: 위반이 나도 좌석 변경이 롤백되지 않게 한다. PostgreSQL은 오류가 난 트랜잭션을 그대로 커밋할 수 없으므로, 예를 들어 예매 줄 INSERT만 SAVEPOINT(`session.begin_nested()`)로 감싸 위반 때 그 부분만 되돌리고 좌석 SOLD 변경은 커밋한 채 409를 돌려주게 한다. `test_unique_violation_rolls_back_seat_state`가 실패하는지 본다. 되돌린다.
4. 원본으로 되돌린 뒤 복사본과 `diff`가 없는지, `git diff backend/`가 T-22 변경뿐인지 확인한다. `uv run pytest` 전체를 돌린다.
5. 테스트는 고치지 않는다. 변형은 저장소에 남기지 않는다.

## 보고
변형별로: 바꾼 내용 한 줄, 실패한 테스트 이름과 실패 메시지(기대/실제), 다른 테스트 영향. 되돌림 확인(diff 결과), 전체 테스트 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
