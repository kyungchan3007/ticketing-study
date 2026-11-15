# T-31 (server) Idempotency-Key 검사를 요청 형식 단계로 — 구현(PASS)

## 배경
- review T-29 지적 1: 키 검사가 홀드 조회 뒤에 있어서, 키 없는 요청이 404·500이 된다. 계약은 키 없음 400 `VALIDATION_ERROR`.
- lead 결정: 검사 순서는 401(`X-User-Id`) → 400(키 없음·공백만) → 홀드 조회(404) → 나머지(T-28 순서 그대로).
- test(T-30)가 `test_internal_error.py`의 확정 DB 장애 테스트에 키를 보내도록 고쳤다. 새 테스트 `test_us04_ac04_12_missing_key_checked_before_hold_lookup`이 지금 FAIL(404). lead가 해시를 기록했다(14개 파일).
- 지적 2(같은 키·다른 좌석 동시)는 테스트만 추가됐고 지금 서버에서 통과한다. `..._overlap_forced` 테스트는 두 요청이 사전 조회를 통과해 삽입에서 겹친다는 전제다. 순서를 바꾸며 이 경로를 없애면 그 테스트가 실패하니, 그 경우 고치지 말고 lead에게 알린다.

## 할 일
- `backend/`만 수정해서 키 검사를 홀드 조회 앞으로 옮긴다. 다른 동작은 바꾸지 않는다.
- `uv run pytest` 전체 통과, `uv run pytest tests/concurrency` 3번 연속 통과.

## 보고
바꾼 줄, 테스트 결과 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
