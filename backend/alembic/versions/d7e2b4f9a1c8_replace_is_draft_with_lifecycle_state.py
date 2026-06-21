"""Replace is_draft boolean with lifecycle_state enum

Revision ID: d7e2b4f9a1c8
Revises: c3d5a8f2e1b9
Create Date: 2026-06-21 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision: str | None = "d7e2b4f9a1c8"
down_revision: str | None = "c3d5a8f2e1b9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add DRAFT and ACTIVE to the existing round_lifecycle_state enum
    op.execute("ALTER TYPE round_lifecycle_state ADD VALUE 'DRAFT'")
    op.execute("ALTER TYPE round_lifecycle_state ADD VALUE 'ACTIVE'")

    # Migrate existing is_draft data into lifecycle_state
    op.execute(
        "UPDATE rounds SET lifecycle_state = 'DRAFT' WHERE is_draft = TRUE AND lifecycle_state IS NULL"
    )
    op.execute(
        "UPDATE rounds SET lifecycle_state = 'ACTIVE' WHERE is_draft = FALSE AND lifecycle_state IS NULL"
    )

    # Make lifecycle_state NOT NULL with a default of ACTIVE
    op.alter_column(
        "rounds",
        "lifecycle_state",
        nullable=False,
        server_default="ACTIVE",
    )

    # Drop the now-redundant is_draft column
    op.drop_column("rounds", "is_draft")


def downgrade() -> None:
    # Re-add is_draft column (nullable first, then populate, then constrain)
    op.add_column("rounds", sa.Column("is_draft", sa.Boolean(), nullable=True))
    op.execute("UPDATE rounds SET is_draft = (lifecycle_state = 'DRAFT')")
    op.alter_column("rounds", "is_draft", nullable=False)

    # Make lifecycle_state nullable again
    op.alter_column("rounds", "lifecycle_state", nullable=True, server_default=None)
    # Note: PostgreSQL does not support removing enum values, so DRAFT and ACTIVE
    # remain in the round_lifecycle_state enum type after downgrade.
