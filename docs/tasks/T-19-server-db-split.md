# T-19 (server) 서버 실행·벤치마크용 DB(tkt_server) 분리

## 배경
벤치마크·실험과 테스트가 같은 `tkt_test`를 쓴다. 동시에 돌면 한쪽이 데이터를 지우고 다른 쪽이 덮어써 테스트 결과가 흔들릴 수 있다.

## 정한 것 (lead)
- 서버 실행과 벤치마크는 `tkt_server`, 테스트는 지금처럼 `tkt_test`. 어느 DB를 쓸지는 `DATABASE_URL`로 고른다.
- `DATABASE_URL`이 없을 때 기본값은 `postgresql+psycopg://tkt:tkt@localhost:5432/tkt_server`.
- `tkt`(compose의 POSTGRES_DB)는 그대로 둔다.

## 할 일
1. `backend/docker/init-db.sql`: DB를 새로 띄울 때 `tkt_server`도 만든다(주석도 맞춘다).
2. `backend/db.py`: `DEFAULT_DATABASE_URL`을 `tkt_server`로.
3. 그 밖에 `tkt`를 기본으로 가정하는 곳(`backend/seed.py`의 `__main__` 등)이 있으면 `database_url()`을 따르게 한다.
4. `backend/`만 수정한다. 테스트는 고치지 않는다. 지금 떠 있는 컨테이너에 `tkt_server`를 만들고 마이그레이션하는 일과 새 컨테이너 확인은 lead가 한다.

## 보고
바꾼 파일과 줄, `uv run pytest` 마지막 줄. 끝에 `정한 것: ...`, `원칙 충돌: ...`. 보고하고 멈춘다. 커밋하지 않는다.
