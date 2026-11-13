"""Store game modes, prompts and power metadata; populated by scripts/seed.py."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_catalog"
down_revision = "0002_trace_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "game_modes",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(32), nullable=False),
        sa.Column("tone", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("fields", JSONB(), nullable=False),
        sa.Column("mix_position", sa.Integer()),
        sa.CheckConstraint(
            "kind IN ('text','image','shared','relay')", name="ck_game_modes_kind"
        ),
        sa.CheckConstraint(
            "position >= 0 AND (mix_position IS NULL OR mix_position >= 0)",
            name="ck_game_modes_position",
        ),
    )
    op.create_table(
        "game_prompts",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column(
            "mode_id", sa.String(63), sa.ForeignKey("game_modes.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_game_prompts_position"),
    )
    op.create_table(
        "game_powers",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(32), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_game_powers_position"),
    )


def downgrade():
    op.drop_table("game_prompts")
    op.drop_table("game_powers")
    op.drop_table("game_modes")
