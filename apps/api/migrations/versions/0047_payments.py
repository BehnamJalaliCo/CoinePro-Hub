"""Prompt 24 (contract §33.2, §33.3): crypto payments, read and reconciled.

- money.payment_sources (§33.2 PaymentSource): where a company's payments are read from. A `ledger`
  source is the company's own records, read through its runner (a `ledger` job, §26; the query
  lives on the company server, this table only holds the cursor and the open job); a `chain`
  source is a public address on BSC or TRON, read through egress (`chain-read`). A chain source
  also remembers how far back and forward its scan covers (`scan_from_at`, `scanned_to_at`), so a
  payment is called `ledger_only` only where the scan really looked.
- money.chain_transfers: what the chain showed (USDT transferred TO an address of the company):
  tx hash, amount (numeric, never a float), block, confirmations, time.
- money.payments (§33.2 Payment): one row per company, source and ext_id. Rows of the ledger carry
  the company's own pseudonymous customer (an HMAC), plan, amount and hash; a transfer nobody
  claimed is a `chain_only` row of its own (no customer, no plan).
- money.reconcile_days (§33.2 Reconcile): one row per company and day, counts by status.
- money.alerts: one row per payment and kind, so a mismatch is told once.
- The hub's runner job kinds (§26.2) gain `ledger` (the runner side is runner 0.3.0).

Every table carries company_id under FORCE RLS as 0042's; nothing is deleted by the app. A fresh
start wipes the payments, transfers, days and alerts (re-read from the sources) and keeps the
sources the owner configured (their cursors and open jobs are reset).

Revision ID: 0047
Revises: 0046
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
TABLES = (
    "money.payment_sources",
    "money.chain_transfers",
    "money.payments",
    "money.reconcile_days",
    "money.alerts",
)
STATUSES = "'matched', 'ledger_only', 'chain_only', 'amount_mismatch', 'pending_chain'"


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
"""


def _job_kinds(add: bool) -> str:
    """Rewrite the `kind` check of infra.server_jobs from what it holds now (a parallel migration
    may have added kinds of its own): add `ledger`, or take it out again (past rows stay: the
    check is then NOT VALID)."""
    merged = (
        "(kinds || ARRAY['ledger'])"
        if add
        else "ARRAY(SELECT k FROM unnest(kinds) k WHERE k <> 'ledger')"
    )
    tail = "" if add else " NOT VALID"
    return f"""
DO $kinds$
DECLARE
    r record;
    kinds text[];
BEGIN
    FOR r IN
        SELECT c.conname, pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        WHERE c.contype = 'c' AND c.conrelid = 'infra.server_jobs'::regclass
    LOOP
        CONTINUE WHEN r.def NOT LIKE '%(kind = ANY%' AND r.def NOT LIKE '%kind IN%';
        SELECT array_agg(DISTINCT m[1]) INTO kinds
        FROM regexp_matches(r.def, '''([a-z_0-9]+)''', 'g') AS m;
        kinds := {merged};
        EXECUTE format('ALTER TABLE infra.server_jobs DROP CONSTRAINT %I', r.conname);
        EXECUTE format('ALTER TABLE infra.server_jobs ADD CONSTRAINT %I CHECK (kind = ANY (ARRAY[%s])){tail}',
                       r.conname, (SELECT string_agg(quote_literal(k), ', ') FROM unnest(kinds) k));
    END LOOP;
END
$kinds$;
"""


UPGRADE = (
    f"""
CREATE SCHEMA money;
GRANT USAGE ON SCHEMA money TO {APP_ROLES};

-- ======================================================== payment sources ==
CREATE TABLE money.payment_sources (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    kind             text NOT NULL CHECK (kind IN ('ledger', 'chain')),
    adapter          text NOT NULL CHECK (adapter ~ '^[a-z][a-z0-9_-]{{1,40}}$'),
    network          text CHECK (network IN ('bsc_usdt', 'trc20_usdt')),
    -- the company's PUBLIC address (chain only); never a key
    address          text CHECK (length(address) BETWEEN 20 AND 80),
    -- a ledger source reads through this runner (null = the company's first online runner)
    server_id        uuid REFERENCES infra.servers (id),
    state            text NOT NULL DEFAULT 'not_configured'
                     CHECK (state IN ('not_configured', 'ok', 'error')),
    enabled          boolean NOT NULL DEFAULT true,
    last_read_at     timestamptz,
    last_error_fa    text CHECK (length(last_error_fa) <= 500),
    -- a ledger source: the runner's opaque cursor and the job in flight
    cursor           text CHECK (length(cursor) <= 200),
    pending_job_id   uuid REFERENCES infra.server_jobs (id),
    -- a chain source: the next block (BSC) or the next millisecond (TRON) to scan, and the span
    -- of time the scan has covered so far
    scan_next        bigint CHECK (scan_next >= 0),
    scan_fingerprint text CHECK (length(scan_fingerprint) <= 500),
    scan_from_at     timestamptz,
    scanned_to_at    timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    version          int NOT NULL DEFAULT 1,
    CHECK ((kind = 'chain') = (address IS NOT NULL AND network IS NOT NULL)),
    CHECK (kind = 'chain' OR (network IS NULL AND address IS NULL))
);
CREATE UNIQUE INDEX payment_sources_ledger ON money.payment_sources (company_id, adapter)
    WHERE kind = 'ledger';
CREATE UNIQUE INDEX payment_sources_chain ON money.payment_sources (company_id, network, address)
    WHERE kind = 'chain';
CREATE INDEX payment_sources_due ON money.payment_sources (last_read_at NULLS FIRST)
    WHERE enabled;
CREATE TRIGGER payment_sources_immutable BEFORE UPDATE ON money.payment_sources
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'kind', 'network', 'address',
                                                      'created_at');
CREATE TRIGGER payment_sources_version BEFORE UPDATE ON money.payment_sources
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();
GRANT SELECT, INSERT ON money.payment_sources TO {APP_ROLES};
GRANT UPDATE (adapter, server_id, state, enabled, last_read_at, last_error_fa, cursor,
              pending_job_id, scan_next, scan_fingerprint, scan_from_at, scanned_to_at,
              updated_at) ON money.payment_sources TO {APP_ROLES};

-- ======================================================== chain transfers ==
CREATE TABLE money.chain_transfers (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    source_id      uuid NOT NULL REFERENCES money.payment_sources (id),
    network        text NOT NULL CHECK (network IN ('bsc_usdt', 'trc20_usdt')),
    tx_hash        text NOT NULL CHECK (length(tx_hash) BETWEEN 32 AND 80 AND tx_hash = lower(tx_hash)),
    idx            int NOT NULL DEFAULT 0 CHECK (idx >= 0),
    from_address   text NOT NULL CHECK (length(from_address) BETWEEN 20 AND 80),
    to_address     text NOT NULL CHECK (length(to_address) BETWEEN 20 AND 80),
    amount_usdt    numeric(30, 8) NOT NULL CHECK (amount_usdt >= 0),
    block          bigint CHECK (block >= 0),
    confirmations  int NOT NULL DEFAULT 0 CHECK (confirmations >= 0),
    at             timestamptz NOT NULL,
    seen_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, tx_hash, idx)
);
CREATE INDEX chain_transfers_hash ON money.chain_transfers (company_id, tx_hash);
CREATE INDEX chain_transfers_recent ON money.chain_transfers (company_id, at DESC);
CREATE TRIGGER chain_transfers_immutable BEFORE UPDATE ON money.chain_transfers
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'source_id', 'network',
                                                      'tx_hash', 'idx', 'from_address', 'to_address',
                                                      'amount_usdt', 'at', 'seen_at');
GRANT SELECT, INSERT ON money.chain_transfers TO {APP_ROLES};
GRANT UPDATE (block, confirmations) ON money.chain_transfers TO {APP_ROLES};

-- ============================================================== payments ==
CREATE TABLE money.payments (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES core.companies (id),
    source_id      uuid NOT NULL REFERENCES money.payment_sources (id),
    ext_id         text NOT NULL CHECK (length(ext_id) BETWEEN 1 AND 140),
    -- 'ledger': a row of the company's records; 'chain': a transfer nobody claimed (chain_only)
    origin         text NOT NULL CHECK (origin IN ('ledger', 'chain')),
    kind           text NOT NULL DEFAULT 'crypto' CHECK (kind IN ('crypto', 'store')),
    customer       text CHECK (customer ~ '^[0-9a-f]{{64}}$'),
    plan           text CHECK (plan ~ '^[a-z0-9][a-z0-9_.-]{{0,59}}$'),
    -- null only for a store's in-app billing (counted, never summed)
    amount_usdt    numeric(30, 8) CHECK (amount_usdt >= 0),
    network        text CHECK (network IN ('bsc_usdt', 'trc20_usdt')),
    tx_hash        text CHECK (length(tx_hash) BETWEEN 32 AND 80 AND tx_hash = lower(tx_hash)),
    paid_at        timestamptz NOT NULL,
    period_start   timestamptz,
    period_end     timestamptz,
    status         text NOT NULL DEFAULT 'pending_chain' CHECK (status IN ({STATUSES})),
    -- what the chain showed for a matched or short payment (the amount that arrived)
    chain_amount   numeric(30, 8) CHECK (chain_amount >= 0),
    note_fa        text CHECK (length(note_fa) <= 300),
    checked_at     timestamptz NOT NULL DEFAULT now(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, source_id, ext_id),
    CHECK ((period_start IS NULL) = (period_end IS NULL)),
    CHECK (period_end IS NULL OR period_end > period_start),
    CHECK (origin = 'chain' OR customer IS NOT NULL),
    CHECK (kind = 'crypto' OR (amount_usdt IS NULL AND network IS NULL AND tx_hash IS NULL))
);
CREATE INDEX payments_hash ON money.payments (company_id, tx_hash) WHERE tx_hash IS NOT NULL;
CREATE INDEX payments_company_paid ON money.payments (company_id, paid_at DESC, id);
CREATE INDEX payments_status ON money.payments (company_id, status, paid_at DESC);
CREATE TRIGGER payments_immutable BEFORE UPDATE ON money.payments
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'source_id', 'ext_id',
                                                      'origin', 'created_at');
-- a payment of the company's ledger is never deleted; the rows the hub derived itself from the
-- chain (`chain_only`) go once a ledger row claims their hash
CREATE FUNCTION money.keep_ledger_rows() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.origin = 'ledger' THEN
        RAISE EXCEPTION 'a payment of the ledger is never deleted' USING ERRCODE = 'HQV01';
    END IF;
    RETURN OLD;
END $$;
CREATE TRIGGER payments_keep_ledger BEFORE DELETE ON money.payments
    FOR EACH ROW EXECUTE FUNCTION money.keep_ledger_rows();
GRANT SELECT, INSERT, DELETE ON money.payments TO {APP_ROLES};
GRANT UPDATE (kind, customer, plan, amount_usdt, network, tx_hash, paid_at, period_start,
              period_end, status, chain_amount, note_fa, checked_at) ON money.payments TO {APP_ROLES};

-- ======================================================= reconcile per day ==
CREATE TABLE money.reconcile_days (
    company_id        uuid NOT NULL REFERENCES core.companies (id),
    day               date NOT NULL,
    ledger_count      int NOT NULL DEFAULT 0 CHECK (ledger_count >= 0),
    chain_count       int NOT NULL DEFAULT 0 CHECK (chain_count >= 0),
    matched           int NOT NULL DEFAULT 0 CHECK (matched >= 0),
    ledger_only       int NOT NULL DEFAULT 0 CHECK (ledger_only >= 0),
    chain_only        int NOT NULL DEFAULT 0 CHECK (chain_only >= 0),
    amount_mismatch   int NOT NULL DEFAULT 0 CHECK (amount_mismatch >= 0),
    pending_chain     int NOT NULL DEFAULT 0 CHECK (pending_chain >= 0),
    note_fa           text NOT NULL DEFAULT '' CHECK (length(note_fa) <= 500),
    computed_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (company_id, day)
);
GRANT SELECT, INSERT ON money.reconcile_days TO {APP_ROLES};
GRANT UPDATE (ledger_count, chain_count, matched, ledger_only, chain_only, amount_mismatch,
              pending_chain, note_fa, computed_at) ON money.reconcile_days TO {APP_ROLES};

-- ================================================================ alerts ==
-- One row per payment and kind: a mismatch is told once. `critical` = the owner was told too.
CREATE TABLE money.alerts (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    -- (no foreign key: a derived `chain_only` row is deleted once a ledger row claims it)
    payment_id  uuid NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('ledger_only', 'chain_only', 'amount_mismatch')),
    critical    boolean NOT NULL DEFAULT false,
    work_ids    uuid[] NOT NULL DEFAULT '{{}}',
    at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_id, kind)
);
CREATE INDEX alerts_recent ON money.alerts (company_id, at DESC);
CREATE TRIGGER alerts_append_only BEFORE UPDATE OR DELETE ON money.alerts
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
GRANT SELECT, INSERT ON money.alerts TO {APP_ROLES};
"""
    + "".join(_rls(t) for t in TABLES)
    + _job_kinds(True)
)

DOWNGRADE = (
    """
DROP TABLE money.alerts;
DROP TABLE money.reconcile_days;
DROP TABLE money.payments;
DROP TABLE money.chain_transfers;
DROP TABLE money.payment_sources;
DROP FUNCTION money.keep_ledger_rows();
DROP SCHEMA money;
-- past `ledger` jobs stay as they are: the narrower check holds for new rows only
"""
    + _job_kinds(False)
)


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
