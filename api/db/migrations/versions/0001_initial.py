"""Create the initial Trace database schema."""

from alembic import op

from api.db.base import Base
from api.db import models as _models

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all initial persistence tables and indexes."""
    tables = [table for table in Base.metadata.sorted_tables if table.name != "users"]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    """Drop the initial schema."""
    tables = [table for table in reversed(Base.metadata.sorted_tables) if table.name != "users"]
    Base.metadata.drop_all(bind=op.get_bind(), tables=tables)
