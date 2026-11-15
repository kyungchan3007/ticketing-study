# T-32 (review) T-29 지적 1·2 반영 재확인

읽기만 한다. 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다).

## 반영 내용
- 지적 1: lead 결정으로 검사 순서를 401 → 400(키 없음·공백만) → 홀드 조회 404 → 나머지로 정했다.
  - 테스트(T-30): `tests/api/test_us04_confirm_booking.py`의 `test_us04_ac04_12_missing_key_checked_before_hold_lookup`(없는 홀드 + 키 없음 → 400. 헤더도 없으면 401이 먼저). 이 테스트는 고치기 전 서버에서 404로 FAIL했다. `tests/api/test_internal_error.py`의 확정 DB 장애 테스트는 키를 보내게 고쳤다(기대값 500 그대로).
  - 구현(T-31): `backend/main.py` `confirm_booking`에서 키 검사를 홀드 조회 앞으로 옮겼다.
- 지적 2: 테스트(T-30) `test_us04_ac04_13_same_key_two_seats_concurrently`(동시 3회), `test_us04_ac04_13_same_key_two_seats_overlap_forced`(커밋하지 않은 (u1, k1) 줄로 두 요청을 삽입 단계에서 기다리게 하고, `pg_stat_activity`로 대기 2건을 확인한 뒤 풀기) 추가. 지금 서버에서 둘 다 통과.
- 결과(lead 확인): 119 passed, concurrency 3번 연속 통과, story_report 80 통과·실패 0, 해시 14개 일치.

## 확인할 것
1. 지적 1·2가 해결됐는가. 키 검사 위치가 다른 판정(같은 키 → 같은 예매, 본인 기존 예매 반환)을 바꾸지 않았는가.
2. `overlap_forced` 테스트가 정말 사전 조회를 통과한 두 요청의 경쟁을 만드는가. 다른 테스트와 섞이거나 잠금이 남을 위험은 없는가.
3. T-29 판정을 바꿀 새 문제가 있는가.

## 보고
번호, 심각도, 내용, 근거(파일:줄), 재현 방법. T-29 지적 1·2 각각 판정(해결/미해결). 끝에 `정한 것: ...`, `원칙 충돌: ...`.
