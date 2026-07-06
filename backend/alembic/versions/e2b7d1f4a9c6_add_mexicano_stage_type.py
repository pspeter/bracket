"""Add MEXICANO value to the stage_type enum

Revision ID: e2b7d1f4a9c6
Revises: b4e8f2a1c9d7
Create Date: 2026-07-06 12:00:00.000000

"""

from alembic import op

revision: str | None = "e2b7d1f4a9c6"
down_revision: str | None = "b4e8f2a1c9d7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Mexicano is a new standings-resolved stage type. The stage_type enum is a native
    # PostgreSQL enum, so the new value has to be registered on the type.
    op.execute("ALTER TYPE stage_type ADD VALUE IF NOT EXISTS 'MEXICANO'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type, so recreate the type without
    # MEXICANO. Any lingering MEXICANO stage items would block the cast, so convert them
    # to SWISS first (both are standings-resolved and share the same round structure).
    op.execute("UPDATE stage_items SET type = 'SWISS' WHERE type = 'MEXICANO'")
    op.execute("ALTER TYPE stage_type RENAME TO stage_type_old")
    op.execute("CREATE TYPE stage_type AS ENUM ('SINGLE_ELIMINATION', 'SWISS', 'ROUND_ROBIN')")
    op.execute(
        "ALTER TABLE stage_items ALTER COLUMN type TYPE stage_type USING type::text::stage_type"
    )
    op.execute("DROP TYPE stage_type_old")
