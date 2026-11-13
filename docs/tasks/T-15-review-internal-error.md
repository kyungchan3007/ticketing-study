# T-15 (review) #17 지적 A 반영 확인

읽기만 한다. 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다). 재현이 필요하면 재현 명령과 기대 결과를 적는다.

## 반영 내용
- 지적 A: 처리하지 못한 예외(예: DB 연결 끊김)가 `500 text/plain`으로 나가 PRD 5절 `{code, message}`와 어긋났다.
- PRD 5절 표, `docs/openapi.yaml`(Error code enum `INTERNAL_ERROR`, `components/responses/InternalError`, 네 operation의 `"500"`) — lead.
- 테스트(T-13): `tests/contract/test_openapi.py` 끝의 `test_internal_error_*` 5개, `tests/api/test_internal_error.py` 4개 — test.
- 구현(T-14): `backend/main.py`의 `@app.exception_handler(Exception)` `_unhandled_error` — server.

## 확인할 것
1. 지적 A가 해결됐는가: DB가 끊긴 상태에서 네 operation이 500·application/json·`{code: INTERNAL_ERROR, message}`인가. message에 내부 정보가 없는가.
2. 테스트가 의미 있는가: 처리기가 없으면 실패하는가(T-13에서 9 failed 확인됨), DB가 없는 상황을 다른 테스트 준비와 섞지 않는가.
3. 새 문제가 없는가: 기존 처리기(ApiError, 422→400, 404/405)가 그대로인가, 예외 원인이 서버 로그에 남는가, 처리기가 잠금·트랜잭션 처리에 영향을 주지 않는가.

## 보고
번호, 심각도, 내용, 근거(파일:줄), 재현 방법을 표로 적고 "해결/미해결"을 판정한다. 끝에 `원칙 충돌: ...`.
