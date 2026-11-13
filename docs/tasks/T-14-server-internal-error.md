# T-14 (server) 처리하지 못한 예외를 500 INTERNAL_ERROR로 — 통과(PASS)

## 배경
#17 지적 A: 처리하지 못한 예외(예: DB 연결 끊김)가 `500 text/plain "Internal Server Error"`로 나간다. PRD 5절은 모든 오류를 `{code, message}`로 정한다.
- PRD 5절과 계약(`docs/openapi.yaml`)에 `500 INTERNAL_ERROR`가 추가됐다(lead). 네 operation 모두 `"500"`은 `components/responses/InternalError`.
- 테스트(T-13, 해시 기록됨): `tests/api/test_internal_error.py` 4개(계약 테스트 5개는 이미 통과).

## 할 일
1. `backend/main.py`에 처리하지 못한 예외를 받는 처리기를 넣어 `500 {"code": "INTERNAL_ERROR", "message": ...}`(application/json)을 돌려준다.
2. `message`에 내부 정보(예외 클래스 이름, DB 주소·사용자·비밀번호)를 넣지 않는다. 원인은 서버 로그로 남긴다.
3. 기존 처리기(ApiError, RequestValidationError, StarletteHTTPException)와 기존 동작은 바꾸지 않는다.
4. `backend/`만 수정한다. 테스트는 고치지 않는다. 테스트가 이상해 보이면 고치지 말고 보고한다.

## 완료 기준
- `uv run pytest` 전체 통과(PASS).
- lead에게 보고: 바꾼 파일과 줄, 테스트 결과 마지막 줄. 보고 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
