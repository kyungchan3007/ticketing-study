# T-34 (server) 긴 Idempotency-Key 500 결함 수정 — 구현(PASS)

## 배경
- 사람 재현: 무작위 3000자 키 → 500 (`index row size 3016 exceeds btree version 4 maximum 2704 for index "uq_bookings_user_key"`).
- 계약(lead): 키는 1~255자, 넘으면 400 `VALIDATION_ERROR`(`docs/openapi.yaml` IdempotencyKey, PRD 5절, US-04 AC-04-14).
- test(T-33)가 테스트를 썼고 lead가 해시를 기록했다(14개 파일). 지금 FAIL 2개: `test_us04_ac04_14_key_256_chars_rejected`(200), `test_us04_ac04_14_key_3000_chars_rejected`(500).

## 할 일
1. 요청 단계에서 키 길이를 검사해 255자 초과면 400 `VALIDATION_ERROR`(검사 순서 401 → 400 → 홀드 조회는 그대로). 길이는 문자 수 기준이다(계약 maxLength).
2. DB에도 길이 제한을 넣을지는 server가 정하고 이유를 보고한다. **마이그레이션으로 넣는다면, 적용 전에 그 길이를 넘는 `idempotency_key`가 DB에 몇 건인지 `tkt_server`에서 확인하고 보고에 적는다**(그 줄을 어떻게 다루는지도). upgrade·downgrade를 실제로 돌려 확인한다.
3. 다른 동작은 바꾸지 않는다. `backend/`만 수정한다. 커밋하지 않는다.

## 완료 기준
`uv run pytest` 전체 통과, `uv run pytest tests/concurrency` 3번 연속 통과. 보고: 바꾼 파일과 줄, DB 제한 여부와 이유, (마이그레이션이면) 적용 전 초과 건수와 upgrade·downgrade 결과, 테스트 결과 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다.
