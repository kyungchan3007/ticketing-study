-- postgres 컨테이너가 처음 뜰 때 한 번 실행된다. tkt 는 POSTGRES_DB 로 이미 만들어진다.
-- tkt_test: 테스트 전용, tkt_server: 서버 실행·벤치마크용(DATABASE_URL 이 없을 때 기본값).
CREATE DATABASE tkt_test OWNER tkt;
CREATE DATABASE tkt_server OWNER tkt;
