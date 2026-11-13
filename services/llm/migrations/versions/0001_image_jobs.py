from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_image_jobs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "image_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("provider_id", sa.String(300)),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", JSONB()),
        sa.Column("error", JSONB()),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
        sa.Column("lease_token", sa.String(32)),
        sa.Column("next_attempt", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("image_jobs")
