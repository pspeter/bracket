"""add signup_team_choice_enabled

Revision ID: f4305c95da09
Revises: f07c72deedfc
Create Date: 2026-04-19 00:49:34.218271

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "f4305c95da09"
down_revision: str | None = "f07c72deedfc"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column(
            "signup_team_choice_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "signup_team_choice_enabled")
