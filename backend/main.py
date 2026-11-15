import logging
import uuid
import weakref
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import clock
from backend.db import database_url, make_engine
from backend.models import Booking, Hold, Performance, Seat

HOLD_SECONDS = 300

logger = logging.getLogger("backend")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    # 모든 오류 본문은 정확히 {code, message} 두 칸이다.
    return JSONResponse(status_code=status, content={"code": code, "message": message})


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_unique_violation(exc: IntegrityError, constraint: str) -> bool:
    """PostgreSQL 고유 위반(SQLSTATE 23505)이면서 제약(또는 유일 인덱스) 이름이 constraint 인 경우만 True."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(exc.orig, "sqlstate", None) == "23505" and getattr(diag, "constraint_name", None) == constraint


def booking_json(booking: Booking) -> dict:
    return {
        "booking_id": booking.booking_id,
        "hold_id": booking.hold_id,
        "performance_id": booking.performance_id,
        "seat_id": booking.seat_id,
        "status": booking.status,
    }


class PaymentCallbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["SUCCEEDED", "FAILED"]


USER_ID_MAX_LENGTH = 255  # 계약(openapi XUserId maxLength)과 같다. 문자 수 기준, 앞뒤 공백을 뗀 값.


def require_user(x_user_id: str | None = Header(default=None)) -> str:
    # 없음·공백뿐·너무 긺은 모두 같은 401 이다(긴 값이 (user_id, idempotency_key) 인덱스 한도를 넘지 않게).
    user_id = x_user_id.strip() if x_user_id is not None else ""
    if not user_id or len(user_id) > USER_ID_MAX_LENGTH:
        raise ApiError(401, "UNAUTHORIZED", "X-User-Id 헤더가 필요합니다.")
    return user_id


IDEMPOTENCY_KEY_MAX_LENGTH = 255  # 계약(openapi IdempotencyKey maxLength)과 같다. 문자 수 기준.


def check_idempotency_key(idempotency_key: str | None) -> str:
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiError(400, "VALIDATION_ERROR", "Idempotency-Key 헤더가 필요합니다.")
    if len(idempotency_key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ApiError(400, "VALIDATION_ERROR", f"Idempotency-Key 는 {IDEMPOTENCY_KEY_MAX_LENGTH}자 이하여야 합니다.")
    return idempotency_key


def create_app() -> FastAPI:
    engine = make_engine(database_url())
    app = FastAPI(title="tkt 좌석 예매 API (MVP)", version="0.1.0")
    app.state.engine = engine
    weakref.finalize(app, engine.dispose)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return error_response(400, "VALIDATION_ERROR", "요청 형식이 올바르지 않습니다.")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return error_response(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), "요청을 처리할 수 없습니다.")

    @app.exception_handler(Exception)
    async def _unhandled_error(request: Request, exc: Exception):
        # 원인은 서버 로그에만 남기고, 응답 message 에는 내부 정보를 넣지 않는다.
        logger.error("처리하지 못한 예외: %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다.")

    def session_of(request: Request) -> Session:
        return Session(request.app.state.engine)

    @app.get("/performances")
    def list_performances(request: Request):
        with session_of(request) as session:
            rows = session.scalars(select(Performance).order_by(Performance.position)).all()
            return {"performances": [{"id": p.id, "title": p.title} for p in rows]}

    @app.get("/performances/{performance_id}/seats")
    def get_seat_map(performance_id: str, request: Request):
        with session_of(request) as session:
            now = clock.get_now()
            if session.get(Performance, performance_id) is None:
                raise ApiError(404, "NOT_FOUND", "공연을 찾을 수 없습니다.")
            seats = session.scalars(
                select(Seat).where(Seat.performance_id == performance_id).order_by(Seat.position)
            ).all()
            hold_ids = [s.current_hold_id for s in seats if s.status == "HELD" and s.current_hold_id]
            expires = (
                {h.hold_id: h.expires_at for h in session.scalars(select(Hold).where(Hold.hold_id.in_(hold_ids)))}
                if hold_ids
                else {}
            )

            def shown(seat: Seat) -> str:
                if seat.status == "HELD":
                    # 만료된 HELD 는 AVAILABLE 로 보인다(현재 시각 >= expires_at).
                    expires_at = expires.get(seat.current_hold_id)
                    return "HELD" if expires_at is not None and now < expires_at else "AVAILABLE"
                return seat.status

            return {
                "performance_id": performance_id,
                "seats": [{"seat_id": s.seat_id, "status": shown(s)} for s in seats],
            }

    def lock_seat(session: Session, performance_id: str, seat_id: str) -> Seat | None:
        return session.scalars(
            select(Seat)
            .where(Seat.performance_id == performance_id, Seat.seat_id == seat_id)
            .with_for_update()
        ).one_or_none()

    @app.post("/performances/{performance_id}/seats/{seat_id}/hold", status_code=201)
    def hold_seat(
        performance_id: str,
        seat_id: str,
        request: Request,
        user_id: str = Depends(require_user),
    ):
        # 좌석 행 잠금 → 판단 → 변경을 한 트랜잭션에서 한다. 나간 뒤에야 다른 요청이 같은 좌석을 본다.
        with session_of(request) as session, session.begin():
            seat = lock_seat(session, performance_id, seat_id)
            if seat is None:
                raise ApiError(404, "NOT_FOUND", "좌석을 찾을 수 없습니다.")
            now = clock.get_now()  # 잠금을 잡은 뒤에 읽는다: 잠금 대기 중 지난 시간이 만료 판단에 반영된다.
            if seat.status == "SOLD":
                raise ApiError(409, "SEAT_ALREADY_SOLD", "이미 팔린 좌석입니다.")
            if seat.status == "HELD":
                current = session.get(Hold, seat.current_hold_id)
                if current is not None and now < current.expires_at:
                    raise ApiError(409, "SEAT_ALREADY_HELD", "이미 홀드된 좌석입니다.")
            hold = Hold(
                hold_id=uuid.uuid4().hex,
                performance_id=performance_id,
                seat_id=seat_id,
                user_id=user_id,
                created_at=now,
                expires_at=now + timedelta(seconds=HOLD_SECONDS),
            )
            session.add(hold)
            session.flush()
            seat.status = "HELD"
            seat.current_hold_id = hold.hold_id
            return {
                "hold_id": hold.hold_id,
                "performance_id": performance_id,
                "seat_id": seat_id,
                "expires_at": iso(hold.expires_at),
            }

    @app.post("/holds/{hold_id}/confirm")
    def confirm_booking(
        hold_id: str,
        request: Request,
        user_id: str = Depends(require_user),
        idempotency_key: str | None = Header(default=None),
    ):
        """예매 요청: 결제 대기(PENDING) 예매를 만들거나 이미 있는 같은 예매를 돌려준다. 좌석은 바꾸지 않는다."""
        # 요청 형식 검사(401 → 400)를 DB 조회보다 먼저 한다.
        idempotency_key = check_idempotency_key(idempotency_key)
        with session_of(request) as session, session.begin():
            hold = session.get(Hold, hold_id)  # 홀드 행은 만들어진 뒤 바뀌지 않는다
            if hold is None:
                raise ApiError(404, "NOT_FOUND", "홀드를 찾을 수 없습니다.")
            # 같은 홀드(=같은 좌석)에 대한 모든 요청을 이 좌석 행 잠금으로 한 줄로 세운다.
            seat = lock_seat(session, hold.performance_id, hold.seat_id)
            now = clock.get_now()  # 잠금 뒤에 한 번만 읽는다.
            same_key = session.scalars(
                select(Booking).where(Booking.user_id == user_id, Booking.idempotency_key == idempotency_key)
            ).one_or_none()
            if same_key is not None:
                if same_key.hold_id == hold.hold_id:
                    return booking_json(same_key)
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 다른 요청에 쓴 Idempotency-Key 입니다.")
            if hold.user_id == user_id:
                # 본인의 같은 홀드에 결제 대기·완료 예매가 있으면 SOLD·만료 판정보다 먼저 그 예매를 돌려준다.
                active = session.scalars(
                    select(Booking)
                    .where(Booking.hold_id == hold.hold_id, Booking.status.in_(("PENDING", "PAID")))
                    .order_by(Booking.created_at)
                ).first()
                if active is not None:
                    return booking_json(active)
            if seat.status == "SOLD":
                raise ApiError(409, "SEAT_ALREADY_SOLD", "이미 팔린 좌석입니다.")
            if hold.user_id != user_id:
                raise ApiError(403, "FORBIDDEN", "다른 사용자의 홀드입니다.")
            if seat.current_hold_id != hold.hold_id or now >= hold.expires_at:
                raise ApiError(409, "HOLD_EXPIRED", "홀드가 만료되었습니다.")
            booking = Booking(
                booking_id=uuid.uuid4().hex,
                hold_id=hold.hold_id,
                performance_id=hold.performance_id,
                seat_id=hold.seat_id,
                user_id=user_id,
                status="PENDING",
                idempotency_key=idempotency_key,
                created_at=now,
            )
            session.add(booking)
            try:
                session.flush()
            except IntegrityError as exc:
                # 다른 좌석(=다른 홀드)에 같은 키를 동시에 쓴 경우: 잠금이 달라 둘 다 통과했다가 여기서 하나가 진다.
                if is_unique_violation(exc, "uq_bookings_user_key"):
                    raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "이미 다른 요청에 쓴 Idempotency-Key 입니다.") from exc
                raise
            return booking_json(booking)

    @app.post("/payments/{booking_id}/callback")
    def payment_callback(booking_id: str, body: PaymentCallbackBody, request: Request):
        """모의 결제사의 결과 콜백. 시각은 좌석 잠금 뒤에 읽어 만료를 판단한다."""
        with session_of(request) as session, session.begin():
            booking = session.get(Booking, booking_id)
            if booking is None:
                raise ApiError(404, "NOT_FOUND", "예매를 찾을 수 없습니다.")
            seat = lock_seat(session, booking.performance_id, booking.seat_id)
            session.refresh(booking)  # 잠금을 기다리는 사이 다른 콜백이 끝냈을 수 있다
            if booking.status != "PENDING":
                return booking_json(booking)  # 끝난 예매는 무엇이 와도 바꾸지 않는다
            now = clock.get_now()  # 잠금 뒤에 한 번만 읽는다.
            if body.result == "FAILED":
                booking.status = "FAILED"
                return booking_json(booking)
            hold = session.get(Hold, booking.hold_id)
            sellable = (
                seat.status != "SOLD" and seat.current_hold_id == booking.hold_id and now < hold.expires_at
            )
            if sellable:
                try:
                    with session.begin_nested():  # SAVEPOINT: 위반 때 이 부분만 되돌린다
                        booking.status = "PAID"
                        session.flush()
                except IntegrityError as exc:
                    # 이미 다른 PAID 줄이 있다 = 팔 수 없음. 다른 제약·DB 오류는 그대로 올려 500 처리.
                    if not is_unique_violation(exc, "uq_bookings_seat"):
                        raise
                    sellable = False
                else:
                    seat.status = "SOLD"
            if not sellable:
                booking.status = "REFUND_REQUIRED"  # 좌석은 바꾸지 않는다
            return booking_json(booking)

    return app


app = create_app()
