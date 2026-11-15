# T-37 (server) 긴 X-User-Id 500 경로 수정 — 구현(PASS)

## 배경
- review T-35: `uq_bookings_user_key`(user_id, idempotency_key)는 user_id 길이 제한이 없어서, 압축되지 않는 긴 `X-User-Id`로 예매 요청하면 btree 한도 초과로 500.
- 사람 결정(Q10 일부), lead 정리: `X-User-Id`는 1~255자, 공백뿐이거나 255자 초과면 401 `UNAUTHORIZED`(헤더 없음과 같게). 홀드·예매 요청 모두. PRD 4·5·10절, `docs/openapi.yaml` XUserId, US-04 AC-04-16.
- test(T-36) 테스트, lead 해시 기록(14개 파일). 지금 FAIL 3개: `test_us04_ac04_16_user_id_256_chars_cannot_hold`(201), `..._3000_chars_cannot_confirm`(403), `..._3000_chars_owner_cannot_confirm`(500).

## 할 일
- `backend/`의 `require_user`에서 길이(문자 수) 검사를 더한다. 검사 순서 401 → 400(키) → 홀드 조회는 그대로. 다른 동작은 바꾸지 않는다.
- DB 제한은 T-34와 같은 판단이면 넣지 않아도 된다(이유를 적는다). 마이그레이션을 넣는다면 적용 전 255자 초과 `user_id`가 `bookings`·`holds`에 몇 건인지 `tkt_server`에서 확인해 적는다.
- `uv run pytest` 전체 통과, `uv run pytest tests/concurrency` 3번 연속 통과.

## 보고
바꾼 줄, DB 제한 여부와 이유, 테스트 결과 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
