import logging
import uuid
import weakref
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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


def is_unique_booking_violation(exc: IntegrityError) -> bool:
    """PostgreSQL 고유 위반(SQLSTATE 23505)이면서 제약 이름이 uq_bookings_seat 인 경우만 True."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(exc.orig, "sqlstate", None) == "23505" and getattr(diag, "constraint_name", None) == "uq_bookings_seat"


def require_user(x_user_id: str | None = Header(default=None)) -> str:
    if x_user_id is None or not x_user_id.strip():
        raise ApiError(401, "UNAUTHORIZED", "X-User-Id 헤더가 필요합니다.")
    return x_user_id.strip()


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
    ):
        with session_of(request) as session, session.begin():
            hold = session.get(Hold, hold_id)
            if hold is None:
                raise ApiError(404, "NOT_FOUND", "홀드를 찾을 수 없습니다.")
            seat = lock_seat(session, hold.performance_id, hold.seat_id)
            now = clock.get_now()  # 잠금 뒤에 한 번만 읽는다.
            if seat.status == "SOLD":
                raise ApiError(409, "SEAT_ALREADY_SOLD", "이미 팔린 좌석입니다.")
            if hold.user_id != user_id:
                raise ApiError(403, "FORBIDDEN", "다른 사용자의 홀드입니다.")
            if seat.current_hold_id != hold.hold_id or now >= hold.expires_at:
                raise ApiError(409, "HOLD_EXPIRED", "홀드가 만료되었습니다.")
            seat.status = "SOLD"
            session.add(
                Booking(
                    hold_id=hold.hold_id,
                    performance_id=hold.performance_id,
                    seat_id=hold.seat_id,
                    user_id=user_id,
                    created_at=now,
                )
            )
            try:
                session.flush()  # 예매 줄을 지금 넣어 UNIQUE 위반을 이 안에서 잡는다.
            except IntegrityError as exc:
                # uq_bookings_seat 위반(= 이미 팔린 좌석)만 409 로 바꾼다. 다른 제약·DB 오류는 그대로 올려 500 처리.
                if is_unique_booking_violation(exc):
                    raise ApiError(409, "SEAT_ALREADY_SOLD", "이미 팔린 좌석입니다.") from exc
                raise
            return {
                "hold_id": hold.hold_id,
                "performance_id": hold.performance_id,
                "seat_id": hold.seat_id,
                "status": "SOLD",
            }

    return app


app = create_app()
