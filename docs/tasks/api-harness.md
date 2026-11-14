# API 테스트와 서버가 맞춰야 할 접점

test(T-01)와 server(T-02)가 이 문서를 같이 따른다. 바꿔야 하면 직접 바꾸지 말고 lead에게 요청한다.
HTTP 경로·상태 코드·오류 code는 `docs/openapi.yaml`이 정한다. 이 문서는 그 밖의 파이썬 접점만 정한다.

## 1. 앱
- `backend/`는 파이썬 패키지다(`backend/__init__.py`). 루트에서 `import backend`가 된다(pytest `pythonpath = ["."]`).
- `backend.main.create_app() -> fastapi.FastAPI`
  - 호출할 때 환경변수 `DATABASE_URL`을 읽는다. 없으면 `postgresql+psycopg://tkt:tkt@localhost:5432/tkt_server`.
- `backend.main.app = create_app()` (uvicorn 진입점 `backend.main:app`).

## 2. 시각
- 서버는 현재 시각을 **`backend.clock.get_now() -> datetime` 하나로만** 읽는다. 반환값은 UTC 기준 timezone-aware `datetime`이다.
- 서버는 `from backend import clock` 후 **`clock.get_now()`처럼 모듈을 거쳐** 부른다(`from backend.clock import get_now`로 이름을 복사하지 않는다). 다른 곳에서 `datetime.now()`, `time.time()`, DB `now()`로 시각을 읽지 않는다.
- 홀드·확정에서 시각은 **좌석 잠금을 잡은 뒤** 한 번만 읽고, 그 값으로 만료를 판단한다(T-03 리뷰 #1). FastAPI 의존성(`Depends(get_now)`)으로 받지 않는다. 의존성은 핸들러 전에, 즉 잠금 전에 풀리기 때문이다.
- 테스트는 `monkeypatch.setattr(backend.clock, "get_now", <함수>)`로 바꿔 끼운다.
- **테스트 전용 HTTP 경로는 만들지 않는다.**

## 3. DB 준비(파이썬 함수, HTTP 아님)
- `backend.db.migrate(database_url: str) -> None`: 마이그레이션을 최신(head)까지 적용한다. 여러 번 불러도 된다.
- `backend.seed.reset(database_url: str, performances: list[dict]) -> None`: 모든 데이터(예매·홀드·좌석·공연)를 지우고 주어진 공연과 좌석만 넣는다. 모든 좌석은 AVAILABLE로 시작한다.
  ```python
  reset(url, [
      {"id": "P1", "title": "공연 A", "seats": ["A1", "A2", "A3"]},
      {"id": "P2", "title": "공연 B", "seats": ["B1"]},
  ])
  reset(url, [])   # 공연 0개
  ```
- `backend.seed.lock_seat(database_url: str, performance_id: str, seat_id: str)`: 컨텍스트 매니저. 별도 연결에서 그 좌석 행을 서버와 같은 방식으로 잠그고, `with` 블록이 끝나면 놓는다. 잠금 대기 상황을 테스트에서 재현하기 위한 것이다.
- `backend.seed.load_default(database_url: str) -> None`: 개발용 기본 시드(공연 1개, 좌석 100석)를 넣는다. `uv run python -m backend.seed`로도 실행한다.

## 4. 테스트용 DB
- `docker compose up -d --wait`로 루트 `docker-compose.yml`의 PostgreSQL을 띄운다(헬스체크 포함).
- 서버 실행·벤치마크 DB는 `tkt_server`, 테스트 DB는 `tkt_test`. compose가 처음 뜰 때 둘 다 만든다(`tkt`는 compose 기본 DB로만 남는다). 테스트와 벤치마크가 동시에 돌아도 서로의 데이터를 지우지 않게 나눴다.
- 벤치마크·실험은 `DATABASE_URL=postgresql+psycopg://tkt:tkt@localhost:5432/tkt_server`로 돌리고, `tkt_test`를 쓰지 않는다.
- 테스트는 환경변수 `TEST_DATABASE_URL`(없으면 `postgresql+psycopg://tkt:tkt@localhost:5432/tkt_test`)을 쓰고, `create_app()` 전에 `DATABASE_URL`을 그 값으로 맞춘다.
- DB에 연결할 수 없으면 테스트는 **건너뛰지 않고 실패**한다. 실패 메시지에 `docker compose up -d --wait`를 안내한다.

## 5. 실행
```bash
docker compose up -d --wait
uv sync
uv run pytest
uv run python scripts/story_report.py
```
