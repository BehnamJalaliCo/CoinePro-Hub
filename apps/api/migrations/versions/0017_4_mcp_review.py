"""Prompt 07.1 §2.10-§2.16 and §3 (MCP): what the review of the MCP bridge needs.

  - tools.mcp_servers:
      - auth_scheme dropped (never used: `auth_header` alone names the header).
      - listing / listed_sha256: the server's latest listing as the gateway
        saw it ([{name, description, sha256}], one digest per tool), pinned
        or not; `listed_tools` (names) stays for the old readers.
      - pinned: the listing the owner sealed (the first one after an enable,
        or the one a `tool_enable` card approved), so a later listing is
        diffed tool by tool (added, removed, changed).
      - secret_reset_at: set when a registration moves the server to another
        host; a secret written in OpenBao before it is no secret of this
        server any more (has_secret false, nothing sent) until the owner
        writes it again (`make mcp-secret`).
  - tools.mcp_calls.outcome gains 'approved': one approved A3 card consumed
    by the one call it allows. The unique index on decision_id (outcome
    'approved') is what makes the consumption atomic: a card runs once.
  - cartable.decisions.kind gains 'tool_enable' (contract §18.10, §18.13):
    a server whose listing changed is switched off and this card asks the
    owner to seal exactly that listing.
  - An index for the A3 cards of MCP calls (company, arguments' hash).

Revision ID: 0017_4 (review 7.1; the parent re-chains it at merge)
Revises: 0017_2
Create Date: 2026-10-22
"""

from hq_api.migration_sql import execute_script

revision = "0017_4"
down_revision = "0017_2"
branch_labels = None
depends_on = None

KINDS = (
    "'hire', 'dismissal', 'recurring_approval', 'deploy', 'a3_action', 'proposal', "
    "'budget_change', 'evaluation', 'code_session'"
)
HEX = "'^[0-9a-f]{64}$'"


def upgrade() -> None:
    execute_script(
        f"""
        ALTER TABLE tools.mcp_servers DROP COLUMN auth_scheme;
        ALTER TABLE tools.mcp_servers
            ADD COLUMN listing jsonb CHECK (jsonb_typeof(listing) = 'array'),
            ADD COLUMN listed_sha256 text CHECK (listed_sha256 ~ {HEX}),
            ADD COLUMN pinned jsonb CHECK (jsonb_typeof(pinned) = 'array'),
            ADD COLUMN secret_reset_at timestamptz;
        COMMENT ON COLUMN tools.mcp_servers.listing IS
            'The latest listing the gateway saw: [{{name, description, sha256}}]';
        COMMENT ON COLUMN tools.mcp_servers.pinned IS
            'The sealed listing (listing_sha256): [{{name, description, sha256}}]';
        COMMENT ON COLUMN tools.mcp_servers.secret_reset_at IS
            'The host changed: an OpenBao secret older than this is not used';

        ALTER TABLE tools.mcp_calls DROP CONSTRAINT mcp_calls_outcome_check;
        ALTER TABLE tools.mcp_calls ADD CONSTRAINT mcp_calls_outcome_check
            CHECK (outcome IN ('resolved', 'decision', 'approved'));
        CREATE UNIQUE INDEX mcp_calls_card_once ON tools.mcp_calls (decision_id)
            WHERE outcome = 'approved';

        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS}, 'tool_enable')) NOT VALID;  -- the head validates (0023)
        CREATE INDEX decisions_mcp_call ON cartable.decisions
            (company_id, (payload ->> 'args_sha256'), created_at DESC)
            WHERE kind = 'a3_action' AND payload ->> 'action' = 'mcp_call';
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        DROP INDEX cartable.decisions_mcp_call;
        -- NOT VALID: past tool_enable cards stay (resolutions point at them); new ones are refused.
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS})) NOT VALID;
        DROP INDEX tools.mcp_calls_card_once;
        ALTER TABLE tools.mcp_calls DROP CONSTRAINT mcp_calls_outcome_check;
        ALTER TABLE tools.mcp_calls ADD CONSTRAINT mcp_calls_outcome_check
            CHECK (outcome IN ('resolved', 'decision')) NOT VALID;
        ALTER TABLE tools.mcp_servers
            DROP COLUMN secret_reset_at, DROP COLUMN pinned, DROP COLUMN listed_sha256,
            DROP COLUMN listing;
        ALTER TABLE tools.mcp_servers ADD COLUMN auth_scheme text CHECK (length(auth_scheme) <= 20);
        """
    )
