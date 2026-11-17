"""A set of slides in one ChatGPT chat (the owner, 2026-11-17: «چت جی پی تی میتونه ۱۰ الی ۱۵ عکس رو
یکجا طراحی بکنه و تحویل بده در اسلاید های مجزا و جداگانه و فقط باید ازش بخواهی»).

- substitutes.calls.images: how many pictures one image call asks for (1, as before; up to 15 for
  a set of story slides). The worker runs a call of more than one as ChatGPT's `slides` task, and
  its creative keeps every picture (file_ids in order).

Additive: the downgrade drops the column.

Revision ID: 0068
Revises: 0067
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE substitutes.calls ADD COLUMN images smallint NOT NULL DEFAULT 1
    CHECK (images BETWEEN 1 AND 15);
"""

DOWNGRADE = """
ALTER TABLE substitutes.calls DROP COLUMN images;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
