"""add self signup columns

Revision ID: f07c72deedfc
Revises: c1ab44651e79
Create Date: 2026-04-19 00:16:15.832500

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "f07c72deedfc"
down_revision: str | None = "c1ab44651e79"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("signup_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("tournaments", sa.Column("signup_token", sa.String(), nullable=True))
    op.add_column(
        "tournaments",
        sa.Column("max_team_size", sa.Integer(), nullable=False, server_default="4"),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "signup_enabled")
    op.drop_column("tournaments", "signup_token")
    op.drop_column("tournaments", "max_team_size")
