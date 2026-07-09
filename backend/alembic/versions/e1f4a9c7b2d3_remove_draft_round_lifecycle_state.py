"""Remove DRAFT from round_lifecycle_state enum

Revision ID: e1f4a9c7b2d3
Revises: d7e2b4f9a1c8
Create Date: 2026-06-22 22:30:00.000000

"""

from alembic import op

revision: str | None = "e1f4a9c7b2d3"
down_revision: str | None = "d7e2b4f9a1c8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # The draft-round flow has been removed, so retire the DRAFT lifecycle state.
    # Migrate any lingering DRAFT rounds to ACTIVE first.
    op.execute("UPDATE rounds SET lifecycle_state = 'ACTIVE' WHERE lifecycle_state = 'DRAFT'")

    # PostgreSQL cannot drop a value from an enum type, so recreate the type without DRAFT.
    op.execute("ALTER TABLE rounds ALTER COLUMN lifecycle_state DROP DEFAULT")
    op.execute("ALTER TYPE round_lifecycle_state RENAME TO round_lifecycle_state_old")
    op.execute(
        "CREATE TYPE round_lifecycle_state AS ENUM ('ACTIVE', 'PLACEHOLDER', 'RESOLVED', 'LOCKED')"
    )
    op.execute(
        "ALTER TABLE rounds ALTER COLUMN lifecycle_state "
        "TYPE round_lifecycle_state "
        "USING lifecycle_state::text::round_lifecycle_state"
    )
    op.execute("ALTER TABLE rounds ALTER COLUMN lifecycle_state SET DEFAULT 'ACTIVE'")
    op.execute("DROP TYPE round_lifecycle_state_old")


def downgrade() -> None:
    # Re-add DRAFT to the enum. ALTER TYPE ... ADD VALUE cannot be used in the same
    # transaction as the new value itself, and the next downgrade (d7e2b4f9a1c8) reads
    # 'DRAFT' within the same `alembic downgrade` transaction, so recreate the type
    # with DRAFT included instead of adding it in place.
    op.execute("ALTER TABLE rounds ALTER COLUMN lifecycle_state DROP DEFAULT")
    op.execute("ALTER TYPE round_lifecycle_state RENAME TO round_lifecycle_state_old")
    op.execute(
        "CREATE TYPE round_lifecycle_state AS ENUM "
        "('DRAFT', 'ACTIVE', 'PLACEHOLDER', 'RESOLVED', 'LOCKED')"
    )
    op.execute(
        "ALTER TABLE rounds ALTER COLUMN lifecycle_state "
        "TYPE round_lifecycle_state "
        "USING lifecycle_state::text::round_lifecycle_state"
    )
    op.execute("ALTER TABLE rounds ALTER COLUMN lifecycle_state SET DEFAULT 'ACTIVE'")
    op.execute("DROP TYPE round_lifecycle_state_old")
