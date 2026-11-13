"""Persist ingress trace context with durable image work."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_trace_context"
down_revision = "0001_game"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "image_requests",
        sa.Column(
            "trace_context",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("image_requests", "trace_context")
