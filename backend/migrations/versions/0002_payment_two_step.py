"""결제 두 단계: bookings 를 예매 하나당 한 줄로 바꾼다

- booking_id 기본 키, status, idempotency_key 추가
- uq_bookings_seat: 전체 UNIQUE → status = 'PAID' 부분 UNIQUE
- uq_bookings_active_hold, uq_bookings_user_key 추가

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("booking_id", sa.String, nullable=True))
    op.add_column("bookings", sa.Column("status", sa.String, nullable=True))
    op.add_column("bookings", sa.Column("idempotency_key", sa.String, nullable=True))
    # 0001 의 예매는 확정 즉시 팔린 것이므로 PAID 로 옮긴다.
    op.execute(
        "UPDATE bookings SET booking_id = hold_id, status = 'PAID', idempotency_key = 'legacy-' || hold_id"
    )
    op.alter_column("bookings", "booking_id", nullable=False)
    op.alter_column("bookings", "status", nullable=False)
    op.alter_column("bookings", "idempotency_key", nullable=False)
    op.drop_constraint("bookings_pkey", "bookings", type_="primary")
    op.create_primary_key("bookings_pkey", "bookings", ["booking_id"])
    op.drop_constraint("uq_bookings_seat", "bookings", type_="unique")
    op.create_check_constraint(
        "ck_bookings_status", "bookings", "status IN ('PENDING', 'PAID', 'FAILED', 'REFUND_REQUIRED')"
    )
    op.create_index(
        "uq_bookings_seat",
        "bookings",
        ["performance_id", "seat_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PAID'"),
    )
    op.create_index(
        "uq_bookings_active_hold",
        "bookings",
        ["hold_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'PAID')"),
    )
    op.create_unique_constraint("uq_bookings_user_key", "bookings", ["user_id", "idempotency_key"])


def downgrade() -> None:
    # 0001 은 PAID 만 표현할 수 있어서 PAID 가 아닌 줄(결제 대기·실패·환불 필요)은 버린다.
    op.execute("DELETE FROM bookings WHERE status <> 'PAID'")
    op.drop_constraint("uq_bookings_user_key", "bookings", type_="unique")
    op.drop_index("uq_bookings_active_hold", table_name="bookings")
    op.drop_index("uq_bookings_seat", table_name="bookings")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.drop_constraint("bookings_pkey", "bookings", type_="primary")
    op.drop_column("bookings", "idempotency_key")
    op.drop_column("bookings", "status")
    op.drop_column("bookings", "booking_id")
    op.create_primary_key("bookings_pkey", "bookings", ["hold_id"])
    op.create_unique_constraint("uq_bookings_seat", "bookings", ["performance_id", "seat_id"])
