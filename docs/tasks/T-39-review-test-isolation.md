# T-39 (review) 테스트 격리 — 순서를 바꾸면 깨지는 테스트 찾기

읽기만 한다. 직접 돌릴 수 없으니 결과는 자기 화면에 남긴다(lead가 transcript로 읽는다).

## 목적
테스트가 실행 순서에 따라 깨지지 않는지 코드로 확인한다. 서버 코드는 바꾸지 않는다.

## 볼 곳
- `tests/api/conftest.py`: 세션 fixture `db_url`, 테스트마다 쓰는 `env`(DB 초기화 `reset`, 시계 `at`, `key`).
- `tests/concurrency/conftest.py`: 세션 fixture `db_url`, `server`(실제 서버 하나를 세션 동안 띄움). `tests/concurrency/test_concurrency.py`의 동시 홀드·동시 확정·동시 콜백 테스트.
- `tests/api/test_unique_violation.py`(임시 인덱스 `zz_test_one_paid_per_performance`), `tests/api/test_internal_error.py`, `tests/capacity/`, `tests/contract/`, `tests/test_smoke.py`.

## 확인할 것
1. 테스트 사이에 공유되는 상태가 있는가: 세션 fixture에 기억해 둔 ID·URL, 모듈 전역 변수, DB를 비우는 시점(테스트 시작 전인지 끝난 뒤인지, 어떤 표를 비우는지), 실패 시 정리되지 않는 것(임시 인덱스, 남은 홀드·예매, 시계 고정값, 환경 변수).
2. `tests/api`와 `tests/concurrency`가 같은 DB를 쓰는가. 섞어 돌리면 서로의 데이터를 보는가.
3. 그래서 순서를 바꾸면 실패할 수 있는 테스트가 있는가.

## 보고
번호, 심각도(높음·중간·낮음), 내용, 근거(파일:줄), **의심되는 순서와 재현 명령**(`uv run pytest <노드1> <노드2> -p no:cacheprovider` 같은 형태, 기대 결과). 의심 없음이면 그렇게 적고 이유를 적는다. 끝에 `정한 것: ...`, `원칙 충돌: ...`.
