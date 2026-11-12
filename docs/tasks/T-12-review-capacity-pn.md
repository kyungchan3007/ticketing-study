# T-12 (review) T-10 지적 #4 반영 재확인

파일은 수정하지 않는다. 읽기와 `uv run python scripts/capacity.py`, `uv run pytest tests/capacity` 실행만 한다.

반영: 매진 안내 기간 `Pn`(`U − N > 0`이면 `P`, `N = U`이면 0)을 두고 폴링·API 합계 기간을 `T + Pn`으로 바꿈. `docs/capacity.md` 3.2절, `docs/decisions.md` [가정 G6] 줄, `scripts/capacity.py`, `tests/capacity/test_capacity.py`(test가 먼저 고쳐 FAIL 확인, lead 해시 기록).

확인: #4가 취지대로 반영됐는가, 기본값 숫자(630초 등)는 그대로인가, T-10에서 "반영됨"으로 본 #1~#3이 깨지지 않았는가, 새 문제가 있는가.
보고: T-10과 같은 표로 `rig send dev-lead@tkt`. 보고하고 멈춘다.
