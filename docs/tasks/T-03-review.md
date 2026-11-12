# T-03 (review) 계약과 구현 비교 리뷰

## 할 일
- **파일은 수정하지 않는다.** 읽기와 테스트 실행(`docker compose up -d --wait`, `uv run pytest`, `uv run python scripts/story_report.py`)만 한다. 필요하면 앱에 직접 요청을 보내 재현해도 된다(데이터를 바꿔도 되는 곳은 테스트 DB `tkt_test`뿐).
- `docs/openapi.yaml`(계약), `docs/PRD.md`, `docs/stories/`, `docs/tasks/api-harness.md`와 `backend/` 구현, `tests/api/`를 비교한다.

## 중점
1. **테스트에 없는 오류 응답**: 계약에 없는 상태 코드나 `{code, message}` 형식이 아닌 응답(예: FastAPI 기본 422, 500, 확정 시 없는 hold_id).
2. **요청 검사 순서**: 401 → 404 → 409. 헤더 없음 + 없는 좌석, 헤더 없음 + SOLD 좌석 같은 조합.
3. **잠금과 시각 판단 순서**: 잠금을 잡은 뒤에 상태와 만료를 판단하는가, 같은 요청 안에서 시각을 한 번만 읽는가, 동시 홀드·확정에서 두 번 팔릴 틈이 있는가.
4. **경계값**: `now == expires_at`(만료), 1초 전(유효), SOLD 뒤 시간 경과, 만료 후 재홀드한 좌석의 이전 hold_id 확정.

## 보고 형식
`rig send dev-lead@tkt`로 표 하나를 보낸다. 지적마다 한 줄.

| 번호 | 심각도(높음/중간/낮음) | 내용 | 근거(파일:줄) | 재현 방법(명령 또는 요청과 기대·실제 응답) |

지적이 없으면 "지적 없음"과 확인한 항목을 보낸다. 보고하고 멈춘다.
