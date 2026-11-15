# T-38 (review) T-35 지적 반영 재확인 — 긴 X-User-Id

읽기만 한다. 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다).

## 반영 내용
- T-35 지적 1(중간, 원칙 충돌): `uq_bookings_user_key`의 user_id 무제한 → 긴 X-User-Id로 예매 요청 500. lead가 tkt_server에서 재현.
- 사람 결정(Q10 일부): `X-User-Id`도 길이 제한. lead 정리: 1~255자, 공백뿐·초과면 401 `UNAUTHORIZED`. PRD 4·5·10·11절, `docs/openapi.yaml` XUserId(minLength 1, maxLength 255), US-04 AC-04-16.
- 테스트(T-36): `tests/api/test_us04_confirm_booking.py`의 `test_us04_ac04_16_*`(256자 홀드 401, 3000자 예매 요청 401 두 가지(남의 홀드·SQL로 만든 본인 홀드), 255자 경계), 계약 테스트. 고치기 전 201·403·500으로 FAIL.
- 구현(T-37): `backend/main.py` `require_user`에 255자(앞뒤 공백 뗀 값의 문자 수) 검사. DB 제한은 넣지 않음(T-34와 같은 이유).
- 결과(lead 확인): 133 passed, concurrency 3번 연속 통과, 해시 14개 일치.

## 확인할 것
1. T-35 지적 1이 해결됐는가: user_id 255자 + 키 255자를 합쳐도 btree 한도(약 2704바이트) 안인가(최악의 멀티바이트 포함). 이 인덱스에 다른 무제한 열이 남아 있지 않은가. 다른 btree 인덱스(holds 등)에 같은 문제가 없는가.
2. 401 검사가 모든 쓰기 경로(홀드·예매 요청)에서 DB 전에 일어나는가. 콜백 경로는 사용자 값이 없으니 해당 없음이 맞는가.
3. T-35 판정을 바꿀 새 문제가 있는가.

## 보고
번호, 심각도, 내용, 근거(파일:줄), 재현 방법. T-35 지적 1 판정(해결/미해결). 끝에 `정한 것: ...`, `원칙 충돌: ...`.
