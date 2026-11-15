# T-26 (review) T-23 지적 #1·#2 반영 재확인

읽기만 한다. 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다). 재현이 필요하면 재현 명령과 기대 결과를 적는다.

## 반영 내용
- T-23 지적 #1(위반 뒤 롤백 확인 테스트 없음), #2(다른 IntegrityError가 500으로 남는지 확인 테스트 없음)를 회귀 방지 테스트로 반영했다. 서버 코드는 바꾸지 않았다(T-22 그대로).
- 테스트(T-24): `tests/api/test_unique_violation.py`에 두 개 추가. 지금 서버에서 둘 다 통과.
  - `test_unique_violation_rolls_back_seat_state` (#1): 409 뒤에도 좌석이 HELD이고 u1의 홀드로 남는다. 이어서 u2 홀드 → 409 `SEAT_ALREADY_HELD`.
  - `test_other_integrity_error_stays_500_internal_error` (#2): `bookings_pkey` 위반(SQLSTATE 23505, 제약 이름만 다름) → 500 `INTERNAL_ERROR`.
- 변형 확인(T-25, server가 잠깐 바꾸고 되돌림):
  - 변형 A: 409 조건을 모든 IntegrityError로 넓힘 → #2 테스트만 실패(500 기대, 409 나옴).
  - 변형 B: 예매 줄 추가만 SAVEPOINT로 되돌리고 좌석 SOLD는 커밋한 채 409 → #1 테스트만 실패(HELD 기대, SOLD 남음).
- 최종: `uv run pytest` 84 passed, `verify_tests.py check` 13개 일치, `git diff backend` 깨끗(현재 커밋 59942fb에 포함).

## 확인할 것
1. 두 테스트가 지적 #1·#2를 실제로 막는가. 위 변형 말고도 테스트를 빠져나가는 잘못된 구현이 있는가(예: 제약 이름 비교 없이 SQLSTATE만 보는 구현, 롤백은 되지만 연결이 깨진 채 풀에 돌아가는 경우).
2. #2 재현 방식(`bookings_pkey` 위반을 일으키는 방법)이 테스트 전용 HTTP 경로 없이, 다른 테스트와 섞이지 않게 되어 있는가.
3. 변형 B가 "롤백 누락"의 대표 사례로 적절한가.
4. T-23 판정을 바꿀 새 문제가 있는가.

## 보고
번호, 심각도(높음·중간·낮음), 내용, 근거(파일:줄), 재현 방법(명령과 기대 결과)을 표로. T-23 #1·#2 각각 판정(해결/미해결). 끝에 `정한 것: ...`, `원칙 충돌: ...`.
