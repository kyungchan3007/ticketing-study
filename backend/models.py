from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Performance(Base):
    __tablename__ = "performances"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class Seat(Base):
    """좌석 한 줄이 곧 잠금 단위다. 홀드·확정은 이 행을 FOR UPDATE로 잡고 판단한다."""

    __tablename__ = "seats"

    performance_id: Mapped[str] = mapped_column(ForeignKey("performances.id"), primary_key=True)
    seat_id: Mapped[str] = mapped_column(String, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="AVAILABLE")
    # 현재 유효한 홀드(만료 판정은 읽는 시점에 한다. 만료돼도 행은 그대로 둔다).
    current_hold_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Hold(Base):
    __tablename__ = "holds"
    __table_args__ = (
        ForeignKeyConstraint(["performance_id", "seat_id"], ["seats.performance_id", "seats.seat_id"]),
    )

    hold_id: Mapped[str] = mapped_column(String, primary_key=True)
    performance_id: Mapped[str] = mapped_column(String, nullable=False)
    seat_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Booking(Base):
    """예매 한 줄(결제 두 단계). 한 홀드에 여러 줄일 수 있다(실패 뒤 새 키로 다시 요청).

    제약(0002 마이그레이션이 만든다)
    - uq_bookings_seat: 좌석당 PAID 한 줄(부분 UNIQUE). 이중 판매의 마지막 방어선.
    - uq_bookings_active_hold: 홀드당 PENDING·PAID 한 줄(부분 UNIQUE).
    - uq_bookings_user_key: (user_id, idempotency_key) UNIQUE.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        Index("uq_bookings_seat", "performance_id", "seat_id", unique=True, postgresql_where=text("status = 'PAID'")),
        Index(
            "uq_bookings_active_hold",
            "hold_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'PAID')"),
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_bookings_user_key"),
        ForeignKeyConstraint(["performance_id", "seat_id"], ["seats.performance_id", "seats.seat_id"]),
    )

    booking_id: Mapped[str] = mapped_column(String, primary_key=True)
    hold_id: Mapped[str] = mapped_column(ForeignKey("holds.hold_id"), nullable=False)
    performance_id: Mapped[str] = mapped_column(String, nullable=False)
    seat_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
