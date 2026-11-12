"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performances",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
    )
    op.create_table(
        "seats",
        sa.Column("performance_id", sa.String, sa.ForeignKey("performances.id"), primary_key=True),
        sa.Column("seat_id", sa.String, primary_key=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="AVAILABLE"),
        sa.Column("current_hold_id", sa.String, nullable=True),
        sa.CheckConstraint("status IN ('AVAILABLE', 'HELD', 'SOLD')", name="ck_seats_status"),
    )
    op.create_table(
        "holds",
        sa.Column("hold_id", sa.String, primary_key=True),
        sa.Column("performance_id", sa.String, nullable=False),
        sa.Column("seat_id", sa.String, nullable=False),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["performance_id", "seat_id"], ["seats.performance_id", "seats.seat_id"]),
    )
    op.create_table(
        "bookings",
        sa.Column("hold_id", sa.String, sa.ForeignKey("holds.hold_id"), primary_key=True),
        sa.Column("performance_id", sa.String, nullable=False),
        sa.Column("seat_id", sa.String, nullable=False),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("performance_id", "seat_id", name="uq_bookings_seat"),
        sa.ForeignKeyConstraint(["performance_id", "seat_id"], ["seats.performance_id", "seats.seat_id"]),
    )


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("holds")
    op.drop_table("seats")
    op.drop_table("performances")
