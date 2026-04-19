"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-04-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("venue", sa.String(length=500), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tickets_total", sa.Integer(), nullable=False),
        sa.Column("tickets_remaining", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organizer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_organizer_id"), "events", ["organizer_id"], unique=False)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bookings_customer_id"), "bookings", ["customer_id"], unique=False)
    op.create_index(op.f("ix_bookings_event_id"), "bookings", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bookings_event_id"), table_name="bookings")
    op.drop_index(op.f("ix_bookings_customer_id"), table_name="bookings")
    op.drop_table("bookings")
    op.drop_index(op.f("ix_events_organizer_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
