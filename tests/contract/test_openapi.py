"""API 계약(docs/openapi.yaml)이 스토리의 인수 조건을 지키는지 검사한다.

- 계약 파일(docs/openapi.yaml)이 없으면 전부 실패(RED)한다.
- 테스트 이름은 test_us<스토리번호>_ac<AC번호>_... 형식이고, docstring 첫 줄에 "US-xx / AC-xx-y"를 적는다.
  scripts/story_report.py가 이 이름 규칙으로 스토리별 결과를 센다.
- [열린 질문]이 붙은 인수 조건(AC-02-4, AC-03-7)은 테스트를 만들지 않는다.
  AC-04-4·5·8·9는 6장에서 Q1·Q3·Q4·Q13 이 결정돼 이제 검사한다.

계약이 지켜야 할 이름 규칙(경로·필드 이름은 계약이 정하지만, 테스트가 operation을 찾으려면 필요하다):
  operationId: listPerformances, getSeatMap, holdSeat, confirmBooking, paymentCallback   (스토리 US-01~05)
  (시각 주입·시드 초기화 같은 테스트 전용 경로는 공개 계약에 넣지 않는다. 구현 단계에서 정한다.)
  응답 필드:  공연 id/title, 좌석 id(seat_id)/status, 홀드 hold_id/expires_at
  예매 요청 대상: hold_id (경로 파라미터 또는 요청 본문 필드), 헤더 Idempotency-Key 필수
  콜백 대상:  booking_id (경로 파라미터), 본문 result = SUCCEEDED | FAILED
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


def assert_idempotency_header(op, path_params):
    hs = [p for p in params(op, path_params) if p.get("in") == "header" and p.get("name", "").lower() == "idempotency-key"]
    assert hs, "Idempotency-Key 헤더 파라미터가 없다"
    assert any(p.get("required") is True for p in hs), "Idempotency-Key 가 required: true 가 아니다"


BOOKING_STATUSES = {"PENDING", "PAID", "FAILED", "REFUND_REQUIRED"}


def assert_booking_success(op, expected_status=None):
    """성공 응답이 booking_id 와 예매 상태(PENDING/PAID/FAILED/REFUND_REQUIRED)를 가진다."""
    p = props(success_schema(op))
    assert "booking_id" in p, "성공 응답에 booking_id 가 없다"
    assert "status" in p, "성공 응답에 예매 status 가 없다"
    assert set(p["status"].get("enum", [])) == BOOKING_STATUSES, "예매 status enum 이 PENDING/PAID/FAILED/REFUND_REQUIRED 와 정확히 같지 않다"


def assert_callback_target_and_body(op, path_params):
    assert any(p.get("in") == "path" and p.get("name") == "booking_id" for p in params(op, path_params)), "콜백이 booking_id 경로 파라미터로 예매를 지정하지 않는다"
    body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    assert "result" in props(body), "콜백 본문에 result 가 없다"
    assert set(props(body)["result"].get("enum", [])) == {"SUCCEEDED", "FAILED"}, "result enum 이 SUCCEEDED/FAILED 와 정확히 같지 않다"
    assert "result" in required(body), "콜백 본문에서 result 가 required 가 아니다"


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
    """US-02 / AC-02-2: 좌석맵 status 가 AVAILABLE/HELD/SOLD 를 모두 표현하고 홀드·예매 요청·결제 콜백(SOLD 로 만드는 경로) operation 이 있다"""
    spec = load_spec()
    _, _, seatmap, _ = find_op(spec, "getSeatMap")
    assert_seatmap_schema(seatmap)
    find_op(spec, "holdSeat")
    find_op(spec, "confirmBooking")
    find_op(spec, "paymentCallback")


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
    """US-04 / AC-04-1: 예매 요청 POST, hold_id 로 대상 지정, 2xx 응답에 booking_id 와 예매 상태(PENDING 포함)"""
    spec = load_spec()
    _, method, op, pp = find_op(spec, "confirmBooking")
    assert method == "post"
    assert_booking_success(op)
    assert_confirm_target_is_hold_id(op, pp)
    assert_user_header(op, pp, need=True)
    assert_idempotency_header(op, pp)


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
    """US-04 / AC-04-4: 이미 SOLD 인 좌석의 예매 요청은 409 SEAT_ALREADY_SOLD"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_error(op, "409", "SEAT_ALREADY_SOLD")


def test_us04_ac04_5_concurrent_confirm():
    """US-04 / AC-04-5: 같은 사람의 동시 예매 요청은 모두 2xx 이고 같은 booking_id 를 돌려준다(성공 응답에 booking_id)"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_booking_success(op)


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


def test_us04_ac04_8_other_users_hold_forbidden():
    """US-04 / AC-04-8: 다른 사용자의 홀드로 예매를 요청하면 403 FORBIDDEN"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_error(op, "403", "FORBIDDEN")


def test_us04_ac04_9_hold_not_found():
    """US-04 / AC-04-9: 없는 홀드로 예매를 요청하면 404 NOT_FOUND"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_error(op, "404", "NOT_FOUND")


def test_us04_ac04_10_same_key_same_response():
    """US-04 / AC-04-10: 같은 키로 다시 보내면 같은 응답을 돌려주므로 Idempotency-Key 가 필수 헤더이고 성공 응답이 예매다"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "confirmBooking")
    assert_idempotency_header(op, pp)
    assert_booking_success(op)


def test_us04_ac04_11_paid_booking_returned():
    """US-04 / AC-04-11: 이미 팔린 예매를 다시 요청하면 같은 예매(PAID)를 돌려주므로 성공 응답의 상태에 PAID 가 있다"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_booking_success(op)


def test_us04_ac04_12_missing_idempotency_key():
    """US-04 / AC-04-12: Idempotency-Key 가 없으면 400 VALIDATION_ERROR"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "confirmBooking")
    assert_idempotency_header(op, pp)
    assert_error(op, "400", "VALIDATION_ERROR")


def test_us04_ac04_13_key_reused_for_other_hold():
    """US-04 / AC-04-13: 같은 키를 다른 홀드에 쓰면 409 IDEMPOTENCY_KEY_REUSED"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "confirmBooking")
    assert_error(op, "409", "IDEMPOTENCY_KEY_REUSED")


def test_us04_ac04_14_idempotency_key_length_limit():
    """US-04 / AC-04-14: Idempotency-Key 는 1~255자(minLength 1, maxLength 255)이고 넘으면 400 VALIDATION_ERROR"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "confirmBooking")
    hs = [p for p in params(op, pp) if p.get("in") == "header" and p.get("name", "").lower() == "idempotency-key"]
    assert hs, "Idempotency-Key 헤더 파라미터가 없다"
    schema = hs[0].get("schema", {})
    assert (schema.get("minLength"), schema.get("maxLength")) == (1, 255), f"키 길이 제한이 1~255 가 아니다: {schema}"
    assert_error(op, "400", "VALIDATION_ERROR")


@pytest.mark.parametrize("operation_id", ["holdSeat", "confirmBooking"])
def test_us04_ac04_16_user_id_length_limit(operation_id):
    """US-04 / AC-04-16: X-User-Id 는 1~255자(minLength 1, maxLength 255)이고 넘으면 401 UNAUTHORIZED"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, operation_id)
    hs = [p for p in params(op, pp) if p.get("in") == "header" and p.get("name", "").lower() == "x-user-id"]
    assert hs, "X-User-Id 헤더 파라미터가 없다"
    schema = hs[0].get("schema", {})
    assert (schema.get("minLength"), schema.get("maxLength")) == (1, 255), f"ID 길이 제한이 1~255 가 아니다: {schema}"
    assert_error(op, "401", "UNAUTHORIZED")


# ---------------------------------------------------------------- US-05
def test_us05_ac05_1_callback_success_response():
    """US-05 / AC-05-1: 콜백 POST, booking_id 로 예매 지정, 본문 result(SUCCEEDED/FAILED), 2xx 응답에 booking_id 와 예매 상태"""
    spec = load_spec()
    path, method, op, pp = find_op(spec, "paymentCallback")
    assert method == "post"
    assert_callback_target_and_body(op, pp)
    assert_booking_success(op)


def test_us05_ac05_2_callback_refund_required_state():
    """US-05 / AC-05-2: 만료 뒤 성공 콜백은 2xx 로 응답하고 예매 상태 REFUND_REQUIRED 를 표현할 수 있다(오류 응답이 아니다)"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "paymentCallback")
    assert_booking_success(op)
    assert not [c for c in responses(op) if c in {"409", "410"}], "만료 뒤 성공 콜백은 2xx 여야 해서 409/410 을 선언하지 않는다"


def test_us05_ac05_3_late_success_after_rehold():
    """US-05 / AC-05-3: 다른 사람이 다시 잡은 뒤 늦은 성공 콜백도 2xx 로 응답하고 상태를 돌려준다"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "paymentCallback")
    assert_booking_success(op)


def test_us05_ac05_4_failed_callback():
    """US-05 / AC-05-4: 콜백 본문 result 에 FAILED 가 있고 응답 예매 상태에 FAILED 가 있다"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "paymentCallback")
    assert_callback_target_and_body(op, pp)
    assert_booking_success(op)


def test_us05_ac05_5_duplicate_callback():
    """US-05 / AC-05-5: 같은 콜백이 또 와도 2xx 로 지금 상태를 돌려주므로 오류 응답이 아니라 Booking 을 돌려준다"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "paymentCallback")
    assert_booking_success(op)
    assert not [c for c in responses(op) if c.startswith("409")], "끝난 예매의 중복 콜백은 409 가 아니다"


def test_us05_ac05_6_finished_booking_ignores_other_result():
    """US-05 / AC-05-6: 끝난 예매에 다른 결과가 와도 2xx 로 지금 상태를 돌려준다(콜백에 X-User-Id 가 필요 없다)"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "paymentCallback")
    assert_booking_success(op)
    assert_user_header(op, pp, need=False)


def test_us05_ac05_7_concurrent_callbacks_response():
    """US-05 / AC-05-7: 동시 콜백 20건이 모두 2xx PAID 이려면 성공 응답이 하나이고 예매 상태를 담는다"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "paymentCallback")
    assert_booking_success(op)
    assert len(success_response(op)) == 1, "성공 코드가 하나가 아니다"


def test_us05_ac05_8_callback_booking_not_found():
    """US-05 / AC-05-8: 없는 예매의 콜백은 404 NOT_FOUND"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, "paymentCallback")
    assert_error(op, "404", "NOT_FOUND")


def test_us05_ac05_9_callback_invalid_result():
    """US-05 / AC-05-9: 결과가 없거나 SUCCEEDED·FAILED 가 아니면 400 VALIDATION_ERROR"""
    spec = load_spec()
    _, _, op, pp = find_op(spec, "paymentCallback")
    assert_callback_target_and_body(op, pp)
    assert_error(op, "400", "VALIDATION_ERROR")


# ---------------------------------------------------------------- 공통: 처리하지 못한 예외(T-13)
@pytest.mark.parametrize("operation_id", ["listPerformances", "getSeatMap", "holdSeat", "confirmBooking", "paymentCallback"])
def test_internal_error_500_declared_as_error_schema(operation_id):
    """공통(T-13): 모든 operation 에 500 응답이 {code, message} 오류 스키마이고 code INTERNAL_ERROR 로 명시돼 있다"""
    spec = load_spec()
    _, _, op, _ = find_op(spec, operation_id)
    assert_error(op, "500", "INTERNAL_ERROR")


def test_internal_error_code_in_error_schema_enum():
    """공통(T-13·6장): components.schemas.Error 의 code enum 에 INTERNAL_ERROR, FORBIDDEN, IDEMPOTENCY_KEY_REUSED, VALIDATION_ERROR 가 있다"""
    spec = load_spec()
    code = props(deref(spec, spec["components"]["schemas"]["Error"]))["code"]
    missing = {"INTERNAL_ERROR", "FORBIDDEN", "IDEMPOTENCY_KEY_REUSED", "VALIDATION_ERROR"} - set(code.get("enum", []))
    assert not missing, f"Error.code enum 에 {sorted(missing)} 가 없다: {code.get('enum')}"
