"""Keep the Gateway model stable across retries of one outbox request."""

from alembic import op
import sqlalchemy as sa

revision = "0004_gateway_model"
down_revision = "0003_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("image_requests", sa.Column("gateway_model", sa.String(128)))


def downgrade():
    op.drop_column("image_requests", "gateway_model")
