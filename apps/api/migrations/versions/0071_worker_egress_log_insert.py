"""The worker writes its own egress log rows (2026-11-27): the hourly connections read (Temporal
ConnectionsRead, domain/egress.py) runs as hq_worker and INSERTs into egress.log, but 0016 gave
hq_worker SELECT only, so every run failed «permission denied for table log» (seen since 11-23):
account figures, IG post reads for the best hour and the per-run results were never read.
The row policy log_tenant already covers the app roles; the table stays append-only (triggers).
Revision ID: 0071
Revises: 0070
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("GRANT INSERT ON egress.log TO hq_worker;")


def downgrade() -> None:
    execute_script("REVOKE INSERT ON egress.log FROM hq_worker;")
