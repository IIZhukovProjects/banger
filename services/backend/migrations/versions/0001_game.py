from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_game"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rooms",
        sa.Column("code", sa.String(6), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("state", JSONB(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "image_requests",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "room_code", sa.String(6), sa.ForeignKey("rooms.code"), nullable=False
        ),
        sa.Column("round_id", sa.String(32), nullable=False),
        sa.Column("owner", sa.String(32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("remote_id", sa.String(36)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt", sa.Float(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
        sa.Column("lease_token", sa.String(32)),
    )
    op.create_table(
        "artifacts",
        sa.Column(
            "room_code", sa.String(6), sa.ForeignKey("rooms.code"), primary_key=True
        ),
        sa.Column("filename", sa.String(80), primary_key=True),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("artifacts")
    op.drop_table("image_requests")
    op.drop_table("rooms")
