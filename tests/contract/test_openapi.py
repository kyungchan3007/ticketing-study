"""API 계약(docs/openapi.yaml)이 스토리의 인수 조건을 지키는지 검사한다.

- 계약 파일(docs/openapi.yaml)이 없으면 전부 실패(RED)한다.
- 테스트 이름은 test_us<스토리번호>_ac<AC번호>_... 형식이고, docstring 첫 줄에 "US-xx / AC-xx-y"를 적는다.
  scripts/story_report.py가 이 이름 규칙으로 스토리별 결과를 센다.
- [열린 질문]이 붙은 인수 조건(AC-02-4, AC-03-7, AC-04-8, AC-04-9)은 테스트를 만들지 않는다.
  AC-04-4의 구매자 확인(Q13), AC-04-5의 나머지 9건 응답(Q1)도 검사하지 않는다.

계약이 지켜야 할 이름 규칙(경로·필드 이름은 계약이 정하지만, 테스트가 operation을 찾으려면 필요하다):
  operationId: listPerformances, getSeatMap, holdSeat, confirmBooking   (스토리 US-01~04)
  (시각 주입·시드 초기화 같은 테스트 전용 경로는 공개 계약에 넣지 않는다. 구현 단계에서 정한다.)
  응답 필드:  공연 id/title, 좌석 id(seat_id)/status, 홀드 hold_id/expires_at
  확정 대상:  hold_id (경로 파라미터 또는 요청 본문 필드)
  사용자 헤더: X-User-Id
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "docs" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
STATUSES = {"AVAILABLE", "HELD", "SOLD"}
ID_NAMES = {"id", "performance_id"}
TITLE_NAMES = {"title", "name"}
SEAT_ID_NAMES = {"id", "seat_id"}


# ---------------------------------------------------------------- 도우미
def load_spec():
    if not SPEC_PATH.exists():
        pytest.fail("계약 파일 docs/openapi.yaml 이 없다")
    data = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "openapi.yaml 최상위가 매핑이 아니다"
    assert str(data.get("openapi", "")).startswith("3"), "openapi 3.x 문서가 아니다"
    assert isinstance(data.get("paths"), dict) and data["paths"], "paths 가 비어 있다"
    return data


def deref(spec, node, seen=()):
    """$ref 를 끝까지 풀어서 돌려준다."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref in seen:
                return {}
            target = spec
            for part in ref.lstrip("#/").split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return deref(spec, target, seen + (ref,))
        return {k: deref(spec, v, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(spec, v, seen) for v in node]
    return node


def find_op(spec, operation_id):
    """(path, method, 풀어낸 operation, 풀어낸 path 수준 parameters)."""
    for path, item in spec["paths"].items():
        for method, op in (item or {}).items():
            if method in HTTP_METHODS and isinstance(op, dict) and op.get("operationId") == operation_id:
                return path, method, deref(spec, op), deref(spec, item.get("parameters", []))
    pytest.fail(f"operationId '{operation_id}' 인 operation 이 계약에 없다")


def params(op, path_params):
    return list(path_params) + list(op.get("parameters", []))


def responses(op):
    return {str(k): v for k, v in (op.get("responses") or {}).items()}


def json_schema(resp):
    content = (resp or {}).get("content") or {}
    media = content.get("application/json")
    assert media is not None, "application/json 본문 정의가 없다"
    assert "schema" in media, "본문 schema 가 없다"
    return media["schema"]


def props(schema):
    """allOf 를 합친 properties."""
    out = dict(schema.get("properties", {}))
    for sub in schema.get("allOf", []):
        out.update(props(sub))
    return out


def required(schema):
    out = set(schema.get("required", []))
    for sub in schema.get("allOf", []):
        out |= required(sub)
    return out


def success_response(op):
    ok = {k: v for k, v in responses(op).items() if k.startswith("2")}
    assert ok, "2xx 성공 응답이 정의돼 있지 않다"
    return ok


def success_schema(op):
    return json_schema(next(iter(success_response(op).values())))


def array_items(schema):
    """최상위 배열이거나, 배열 속성 하나를 가진 객체에서 items 를 꺼낸다."""
    if schema.get("type") == "array":
        return schema
    arrays = [s for s in props(schema).values() if s.get("type") == "array"]
    assert len(arrays) == 1, "응답에 배열(목록)이 정확히 하나 있어야 한다"
    return arrays[0]


def assert_user_header(op, path_params, *, need):
    hs = [p for p in params(op, path_params) if p.get("in") == "header" and p.get("name", "").lower() == "x-user-id"]
    if need:
        assert hs, "X-User-Id 헤더 파라미터가 없다"
        assert any(p.get("required") is True for p in hs), "X-User-Id 가 required: true 가 아니다"
    else:
        assert all(p.get("required") is not True for p in hs), "조회는 X-User-Id 를 필수로 요구하면 안 된다"


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _error_schemas(schema):
    for key in ("oneOf", "anyOf"):
        if key in schema:
            return [s for sub in schema[key] for s in _error_schemas(sub)]
    return [schema]


def assert_error(op, status, code):
    """status 응답이 {code, message} 두 칸 오류이고 code 가 명시돼 있다."""
    resp = responses(op).get(status)
    assert resp is not None, f"{status} 응답이 정의돼 있지 않다"
    for s in _error_schemas(json_schema(resp)):
        p = props(s)
        assert set(p) == {"code", "message"}, f"{status} 오류 본문 속성이 정확히 code, message 두 칸이 아니다: {sorted(p)}"
        assert required(s) >= {"code", "message"}, f"{status} 오류 본문에서 code, message 가 required 가 아니다"
        assert s.get("additionalProperties") is False, f"{status} 오류 본문이 additionalProperties: false 가 아니다"
        assert p["code"].get("type") == "string" and p["message"].get("type") == "string"
    named = any(
        (isinstance(n, dict) and (n.get("code") == code or n.get("const") == code or n.get("enum") == [code]))
        for n in _walk(resp)
    )
    assert named, f"{status} 응답에 code '{code}' 가 (example/const/enum 으로) 명시돼 있지 않다"


def assert_hold_success(op):
    schema = success_schema(op)
    p = props(schema)
    assert "hold_id" in p, "홀드 성공 응답에 hold_id 가 없다"
    assert "expires_at" in p, "홀드 성공 응답에 expires_at 이 없다"
    assert p["expires_at"].get("type") == "string" and p["expires_at"].get("format") == "date-time"


def assert_seatmap_schema(op):
    items = array_items(success_schema(op))["items"]
    p = props(items)
    assert SEAT_ID_NAMES & set(p), f"좌석 식별자 필드({sorted(SEAT_ID_NAMES)})가 없다"
    assert "status" in p, "좌석 status 필드가 없다"
    assert set(p["status"].get("enum", [])) == STATUSES, "status enum 이 AVAILABLE/HELD/SOLD 와 정확히 같지 않다"


def assert_confirm_target_is_hold_id(op, path_params):
    in_path = any(p.get("in") == "path" and p.get("name") == "hold_id" for p in params(op, path_params))
    body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    in_body = "hold_id" in props(body)
    assert in_path or in_body, "확정 요청이 hold_id(경로 또는 본문)로 홀드를 지정하지 않는다"


# ---------------------------------------------------------------- US-01
def test_us01_ac01_1_list_performances_success():
    """US-01 / AC-01-1: 공연 목록 GET, 2xx, 공연마다 ID와 제목"""
    spec = load_spec()
    path, method, op, pp = find_op(spec, "listPerformances")
    assert method == "get"
    items = array_items(success_schema(op))["items"]
    p = props(items)
    assert ID_NAMES & set(p), f"공연 ID 필드({sorted(ID_NAMES)})가 없다"
    assert TITLE_NAMES & set(p), f"공연 제목 필드({sorted(TITLE_NAMES)})가 없다"
    assert "{" not in path, "공연 목록 경로에 경로 파라미터가 있으면 안 된다"


def test_us01_ac01_2_list_performances_can_be_empty():
    """US-01 / AC-01-2: 공연이 없으면 빈 배열(2xx)"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "listPerformances")
    arr = array_items(success_schema(op))
    assert arr.get("minItems", 0) == 0, "목록에 minItems 가 있으면 빈 배열이 계약 위반이 된다"


def test_us01_ac01_3_list_performances_header_optional():
    """US-01 / AC-01-3: 헤더가 있어도 없어도 같은 결과(X-User-Id 필수 아님, 401 없음)"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "listPerformances")
    assert_user_header(op, pp, need=False)
    assert "401" not in responses(op), "공연 목록은 401 을 돌려주지 않는다"


# ---------------------------------------------------------------- US-02
def test_us02_ac02_1_seatmap_all_available():
    """US-02 / AC-02-1: 공연별 좌석맵 GET, 2xx, 좌석 id와 status"""
    spec = load_spec()
    path, method, op, pp = find_op(spec, "getSeatMap")
    assert method == "get"
    assert_seatmap_schema(op)
    assert_user_header(op, pp, need=False)


def test_us02_ac02_2_seatmap_mixed_states():
    """US-02 / AC-02-2: 좌석맵 status 가 AVAILABLE/HELD/SOLD 를 모두 표현하고 홀드·확정 operation 이 있다"""
    spec = load_spec()
    _, _, seatmap, _ = find_op(spec, "getSeatMap")
    assert_seatmap_schema(seatmap)
    find_op(spec, "holdSeat")
    find_op(spec, "confirmBooking")


def test_us02_ac02_3_seatmap_scoped_to_performance():
    """US-02 / AC-02-3: 좌석맵 경로가 공연을 경로 파라미터로 지정한다"""
    spec = load_spec()
    path, _, op, pp = find_op(spec, "getSeatMap")
    path_names = [p["name"] for p in params(op, pp) if p.get("in") == "path"]
    assert len(path_names) == 1, f"공연 하나만 경로 파라미터여야 한다: {path_names}"
    assert "{" + path_names[0] + "}" in path


def test_us02_ac02_5_seatmap_header_optional():
    """US-02 / AC-02-5: 헤더가 있어도 없어도 같은 결과(X-User-Id 필수 아님, 401 없음)"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "getSeatMap")
    assert_user_header(op, pp, need=False)
    assert "401" not in responses(op), "좌석맵은 401 을 돌려주지 않는다"


def test_us02_ac02_6_expired_hold_shown_available():
    """US-02 / AC-02-6: 좌석맵 status 가 AVAILABLE/HELD/SOLD 를 구분해 표현한다(만료 시 AVAILABLE 표시)"""
    spec = load_spec()
    _, _, seatmap, _ = find_op(spec, "getSeatMap")
    assert_seatmap_schema(seatmap)


# ---------------------------------------------------------------- US-03
def test_us03_ac03_1_hold_success():
    """US-03 / AC-03-1: 홀드 POST, 2xx, 응답에 hold_id 와 expires_at(date-time)"""
    spec = load_spec()
    path, method, op, pp = find_op(spec, "holdSeat")
    assert method == "post"
    assert_hold_success(op)
    path_names = [p["name"] for p in params(op, pp) if p.get("in") == "path"]
    assert len(path_names) == 2, f"공연과 좌석 두 개가 경로 파라미터여야 한다: {path_names}"
    assert_user_header(op, pp, need=True)


def test_us03_ac03_2_hold_conflict_held():
    """US-03 / AC-03-2: 만료 전 다른 사용자 홀드는 409 SEAT_ALREADY_HELD, 소유 확인용 확정 operation 존재"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "holdSeat")
    assert_error(op, "409", "SEAT_ALREADY_HELD")
    _, _, confirm, _ = find_op(spec, "confirmBooking")
    success_response(confirm)


def test_us03_ac03_3_rehold_after_expiry():
    """US-03 / AC-03-3: 만료 후 재홀드는 2xx, 새 hold_id 와 expires_at, 소유 확인용 확정 operation 존재"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "holdSeat")
    assert_hold_success(op)
    _, _, confirm, _ = find_op(spec, "confirmBooking")
    assert_error(confirm, "409", "HOLD_EXPIRED")


def test_us03_ac03_4_hold_sold_seat():
    """US-03 / AC-03-4: SOLD 좌석 홀드는 409 SEAT_ALREADY_SOLD"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "holdSeat")
    assert_error(op, "409", "SEAT_ALREADY_SOLD")


def test_us03_ac03_5_concurrent_hold():
    """US-03 / AC-03-5: 동시 홀드: 성공 2xx 1건(hold_id)과 나머지 409 SEAT_ALREADY_HELD, 이후 확정 가능"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "holdSeat")
    assert_hold_success(op)
    assert_error(op, "409", "SEAT_ALREADY_HELD")
    _, _, confirm, _ = find_op(spec, "confirmBooking")
    success_response(confirm)


def test_us03_ac03_6_hold_requires_user():
    """US-03 / AC-03-6: 홀드는 X-User-Id 필수, 없으면 401 UNAUTHORIZED"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "holdSeat")
    assert_user_header(op, pp, need=True)
    assert_error(op, "401", "UNAUTHORIZED")


# ---------------------------------------------------------------- US-04
def test_us04_ac04_1_confirm_success():
    """US-04 / AC-04-1: 확정 POST, hold_id 로 대상 지정, 2xx"""
    spec = load_spec()
    _, method, op, pp = find_op(spec, "confirmBooking")
    assert method == "post"
    success_response(op)
    assert_confirm_target_is_hold_id(op, pp)
    assert_user_header(op, pp, need=True)


def test_us04_ac04_2_confirm_expired():
    """US-04 / AC-04-2: 만료된 홀드 확정은 409 HOLD_EXPIRED"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_error(op, "409", "HOLD_EXPIRED")


def test_us04_ac04_3_confirm_with_old_hold_after_rehold():
    """US-04 / AC-04-3: 재홀드된 좌석을 처음 홀드로 확정하면 409 HOLD_EXPIRED (확정은 hold_id 기준)"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "confirmBooking")
    assert_confirm_target_is_hold_id(op, pp)
    assert_error(op, "409", "HOLD_EXPIRED")
    _, _, hold, _ = find_op(spec, "holdSeat")
    assert "hold_id" in props(success_schema(hold)), "재홀드마다 새 hold_id 를 돌려줘야 한다"


def test_us04_ac04_4_confirm_sold_seat():
    """US-04 / AC-04-4: 이미 SOLD 인 좌석 확정은 409 SEAT_ALREADY_SOLD (구매자 확인은 Q13 대기라 제외)"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_error(op, "409", "SEAT_ALREADY_SOLD")


def test_us04_ac04_5_concurrent_confirm():
    """US-04 / AC-04-5: 동시 확정: 2xx 성공 응답이 있다 (나머지 9건의 코드는 Q1 대기라 제외)"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    success_response(op)


def test_us04_ac04_6_hold_then_confirm_race():
    """US-04 / AC-04-6: 홀드(hold_id, 409)→확정(hold_id, 2xx) 흐름이 계약으로 이어진다"""
    spec = load_spec()
    _, _, hold, _ = find_op(spec, "holdSeat")
    assert_hold_success(hold)
    assert_error(hold, "409", "SEAT_ALREADY_HELD")
    _, _, confirm, pp = find_op(spec, "confirmBooking")
    success_response(confirm)
    assert_confirm_target_is_hold_id(confirm, pp)


def test_us04_ac04_7_confirm_requires_user():
    """US-04 / AC-04-7: 확정은 X-User-Id 필수, 없으면 401 UNAUTHORIZED"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "confirmBooking")
    assert_user_header(op, pp, need=True)
    assert_error(op, "401", "UNAUTHORIZED")


# ---------------------------------------------------------------- 공통: 처리하지 못한 예외(T-13)
@pytest.mark.parametrize("operation_id", ["listPerformances", "getSeatMap", "holdSeat", "confirmBooking"])
def test_internal_error_500_declared_as_error_schema(operation_id):
    """공통(T-13): 모든 operation 에 500 응답이 {code, message} 오류 스키마이고 code INTERNAL_ERROR 로 명시돼 있다"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, operation_id)
    assert_error(op, "500", "INTERNAL_ERROR")


def test_internal_error_code_in_error_schema_enum():
    """공통(T-13): components.schemas.Error 의 code enum 에 INTERNAL_ERROR 가 있다"""
    spec = load_spec()
    code = props(deref(spec, spec["components"]["schemas"]["Error"]))["code"]
    assert "INTERNAL_ERROR" in code.get("enum", []), f"Error.code enum 에 INTERNAL_ERROR 가 없다: {code.get('enum')}"
