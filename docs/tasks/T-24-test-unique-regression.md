# T-24 (test) T-23 리뷰 지적 2건: 회귀 방지 테스트

## 배경
T-23 리뷰(둘 다 낮음):
1. UNIQUE 위반 뒤 bookings 줄 수는 확인하지만, 같은 트랜잭션에서 바꾼 좌석 상태가 되돌아가는지(`A1`이 여전히 HELD, 좌석맵에서 HELD, `current_hold_id`가 u1의 홀드)는 확인하지 않는다.
2. `uq_bookings_seat`가 아닌 IntegrityError가 500 `INTERNAL_ERROR`로 남는지 직접 확인하는 테스트가 없다. DB 연결 끊김 테스트는 OperationalError 경로라서, 409로 바꾸는 조건이 넓어지는 회귀를 막지 못한다.

사람 결정: 둘 다 회귀 방지용이라 **지금 서버에서 바로 통과(PASS)해도 된다.** 대신 server가 코드를 일부러 잠깐 바꿨을 때 실패하는지 확인한다(T-25).

## 할 일
1. 지적 1: `tests/api/test_unique_violation.py`의 위반 시나리오 뒤에 좌석 상태가 되돌아갔는지 확인한다(새 테스트로 나눠도 되고 기존 테스트에 더해도 된다. 기존 기대값은 바꾸지 않는다).
2. 지적 2: 확정 중에 `uq_bookings_seat`가 **아닌** IntegrityError가 나면 500 `INTERNAL_ERROR`인지 확인하는 테스트를 쓴다. 재현 방법은 test가 정한다. 같은 SQLSTATE 23505이지만 다른 제약(예: bookings 기본 키 hold_id)이면 "제약 이름까지 보는지"를 함께 지킬 수 있다.
3. 테스트 전용 HTTP 경로는 만들지 않는다. `backend/`는 고치지 않는다. `tests/`만 수정한다.

## 완료 기준
- `uv run pytest` 전체 통과.
- lead에게 보고(CLAUDE.md 보고 형식 표): 바꾼 파일, 새·바뀐 테스트 이름, 재현 방법. 그리고 **server가 어떤 코드 변경으로 이 테스트를 실패시켜 볼 수 있는지**(예: 409 조건을 모든 IntegrityError로 넓힘, 롤백이 안 되게 함) 테스트별로 한 줄씩. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
