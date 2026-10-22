"""Prompt 07.1 §1.2 (and 06.1 §1.4): a PDF's text is extracted outside any
transaction, in a child process with hard limits. The file is recorded first
with files.processing.status = 'processing'; the result ('ready' with or
without text, or 'failed' when the limits stopped the work) is written in a
second transaction, by the api (or by the worker when it resumes a file the
api never finished).

  - hq_api may UPDATE status, text, error, attempts, updated_at of
    files.processing (before: company_id only).
  - hq_worker may also UPDATE text.

Revision ID: 0017_2
Revises: 0017_1
Create Date: 2026-10-18
"""

from hq_api.migration_sql import execute_script

revision = "0017_2"
down_revision = "0017_1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script(
        """
        GRANT UPDATE (status, text, error, attempts, updated_at) ON files.processing TO hq_api;
        GRANT UPDATE (text) ON files.processing TO hq_worker;
        """
    )


def downgrade() -> None:
    execute_script(
        """
        REVOKE UPDATE (text) ON files.processing FROM hq_worker;
        REVOKE UPDATE (status, text, error, attempts, updated_at) ON files.processing FROM hq_api;
        """
    )
