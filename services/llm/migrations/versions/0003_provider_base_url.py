"""Keep the provider address used when each image job was created."""

from alembic import op
import sqlalchemy as sa

revision = "0003_provider_base_url"
down_revision = "0002_trace_context"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("image_jobs", sa.Column("provider_base_url", sa.String(2048)))


def downgrade():
    op.drop_column("image_jobs", "provider_base_url")
