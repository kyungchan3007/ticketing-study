# T-13 (test) 처리하지 못한 예외의 500 응답 형식 — 실패(FAIL)

## 배경
#17 지적 A(중간): DB 연결이 끊기는 것처럼 처리하지 못한 예외가 나면 `500 text/plain "Internal Server Error"`로 나간다. PRD 5절 "모든 오류 응답은 `{code, message}` 두 칸"과 어긋난다.
재현(지적): `DATABASE_URL`을 없는 포트로 두고 `GET /performances`를 보내면 500이 오고 본문이 JSON이 아니다.

## 정한 요구 (lead가 PRD 5절과 계약에 이 테스트 다음에 넣는다)
- 처리하지 못한 예외는 **500**, 본문은 Error 스키마 `{"code": "INTERNAL_ERROR", "message": "<문자열>"}`, `Content-Type: application/json`.
- `message`에는 내부 정보(예외 클래스 이름, DB 주소·비밀번호)가 들어가지 않는다.
- 계약(`docs/openapi.yaml`): Error `code` enum에 `INTERNAL_ERROR`를 추가하고, 네 operation(`listPerformances`, `getSeatMap`, `holdSeat`, `confirmBooking`) 모두 `"500"` 응답을 Error 스키마와 code `INTERNAL_ERROR`로 선언한다.

## 할 일
1. 계약 테스트(`tests/contract/`): 네 operation에 `500` 응답이 Error 스키마이고 code `INTERNAL_ERROR`로 명시돼 있는지 확인한다. 기존 `assert_error` 방식을 따르면 된다.
2. API 테스트(`tests/api/`): 지적의 재현대로 **DB에 연결할 수 없는 앱**으로 요청을 보내 500·JSON·Error 스키마·`INTERNAL_ERROR`·message에 내부 정보 없음을 확인한다.
   - 이 테스트는 의도적으로 DB가 없는 상황이다. 기존 "DB에 연결할 수 없으면 실패" 준비 동작과 섞이지 않게 한다.
   - 네 operation 중 최소 `listPerformances`와 `holdSeat`(헤더 있음)를 확인한다.
   - 테스트 전용 HTTP 경로는 쓰지 않는다. `TestClient`가 서버 예외를 그대로 다시 던지지 않게 하는 설정이 필요할 수 있다.
3. 기존 테스트의 인수 조건과 기대값은 바꾸지 않는다. `tests/`만 수정한다.

## 완료 기준
- `uv run pytest tests/contract tests/api`에서 새 테스트가 실패(FAIL)하고, 기존 테스트는 그대로 통과한다. 실패 이유를 확인한다.
- lead에게 보고: 바꾼 파일, 새 테스트 이름, FAIL 출력 마지막 줄과 이유. 보고 끝에 `정한 것: ...`, `원칙 충돌: ...` 줄을 적는다. 보고하고 멈춘다.
