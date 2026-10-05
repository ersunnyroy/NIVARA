"""Optional TimescaleDB hypertables (no-op on plain PostgreSQL).

Revision ID: 0002_timescale
Revises: 5c9a415c586e
"""
from alembic import op
from sqlalchemy import text

revision = "0002_timescale"
down_revision = "5c9a415c586e"
branch_labels = None
depends_on = None

HYPERTABLES = [("ohlcv", "date"), ("index_ohlcv", "date"), ("option_chain", "date"), ("fno_data", "date")]


def upgrade() -> None:
    bind = op.get_bind()
    available = bind.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")).scalar()
    if not available:
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    for table, col in HYPERTABLES:
        op.execute(f"SELECT create_hypertable('{table}', '{col}', migrate_data => true, if_not_exists => true, "
                   f"chunk_time_interval => INTERVAL '180 days')")


def downgrade() -> None:
    pass  # hypertables cannot be converted back in place; restore from backup if needed
