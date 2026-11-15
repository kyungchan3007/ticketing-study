# T-36 (test) 긴 X-User-Id 500 경로 — 실패(FAIL)

## 배경
- review T-35(미해결, 원칙 충돌): `uq_bookings_user_key`는 (`user_id`, `idempotency_key`) 복합 인덱스라, 키를 255자로 막아도 `X-User-Id`가 압축되지 않는 3000자면 예매 요청이 다시 500(btree 한도 초과)이다. lead가 tkt_server에서 재현했다(홀드 201 → 예매 요청 500).
- 사람 결정(Q10 일부): `X-User-Id`도 길이 제한. lead 정리: 1~255자, 공백뿐이거나 255자 초과면 **401 `UNAUTHORIZED`**(헤더 없음·공백과 같게). PRD 4·5·10절, `docs/openapi.yaml` XUserId(minLength 1, maxLength 255), US-04 AC-04-16.

## 할 일
1. 새 테스트(FAIL이어야 함), US-04 AC-04-16 `test_us04_ac04_16_...`:
   - 256자 `X-User-Id`로 홀드 → 401 `UNAUTHORIZED`, 좌석 AVAILABLE 그대로.
   - 압축되지 않는 3000자 `X-User-Id`로 예매 요청 → 401(지금은 500). 홀드는 정상 사용자로 만든 뒤 긴 사용자로 확정을 보내는 식이면 된다(401이 403보다 먼저다). 예매 줄 0개.
   - 255자 `X-User-Id`로 홀드 2xx, 예매 요청 2xx `PENDING`(경계).
   - 계약 테스트: XUserId minLength 1·maxLength 255.
2. 지금 서버에서 실패하는 이유가 "기능 없음"(256자는 2xx, 3000자 예매는 500)인지 확인한다.
3. 바뀌지 않은 테스트의 기대값은 그대로. `tests/`만 수정, 커밋하지 않는다.

## 보고
CLAUDE.md 보고 형식 표, 바꾼 파일, FAIL 이유. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. lead가 해시를 기록한다.
