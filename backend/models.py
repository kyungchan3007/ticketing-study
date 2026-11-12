from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
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
    """확정 기록. 좌석당 한 줄만 들어갈 수 있다(UNIQUE) — 이중 판매에 대한 마지막 안전망."""

    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("performance_id", "seat_id", name="uq_bookings_seat"),
        ForeignKeyConstraint(["performance_id", "seat_id"], ["seats.performance_id", "seats.seat_id"]),
    )

    hold_id: Mapped[str] = mapped_column(ForeignKey("holds.hold_id"), primary_key=True)
    performance_id: Mapped[str] = mapped_column(String, nullable=False)
    seat_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
