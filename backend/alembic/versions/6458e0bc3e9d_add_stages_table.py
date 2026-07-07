"""Add stages table

Revision ID: 6458e0bc3e9d
Revises: 274385f2a757
Create Date: 2023-04-19 08:59:32.383715

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

from alembic import op

# revision identifiers, used by Alembic.
revision: str | None = "6458e0bc3e9d"
down_revision: str | None = "274385f2a757"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # `stage_type` already exists at this point: it's the enum backing `stage_items.type`,
    # created by the initial baseline migration. `create_type=False` avoids trying (and
    # failing, since checkfirst silently skips label changes) to add the unused
    # `SWISS_DYNAMIC_TEAMS` value that this migration never actually needed.
    op.create_table(
        "stages",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tournament_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "type",
            ENUM(
                "SINGLE_ELIMINATION",
                "SWISS",
                "ROUND_ROBIN",
                name="stage_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            ENUM(
                "COMPLETED",
                "ACTIVE",
                "INACTIVE",
                name="stage_status",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stages_id"), "stages", ["id"], unique=False)

    # Rounds already reach their stage through stage_item_id -> stage_items -> stage_id;
    # tournament_id is a redundant, unused legacy link and can just be dropped.
    op.drop_constraint("rounds_tournament_id_fkey", "rounds", type_="foreignkey")
    op.drop_column("rounds", "tournament_id")

    op.create_foreign_key(None, "stage_items", "stages", ["stage_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("stage_items_stage_id_fkey", "stage_items", type_="foreignkey")

    op.add_column(
        "rounds", sa.Column("tournament_id", sa.BigInteger(), autoincrement=False, nullable=True)
    )
    op.create_foreign_key(
        "rounds_tournament_id_fkey", "rounds", "tournaments", ["tournament_id"], ["id"]
    )

    op.drop_index(op.f("ix_stages_id"), table_name="stages")
    op.drop_table("stages")
    op.execute("DROP TYPE stage_status")
