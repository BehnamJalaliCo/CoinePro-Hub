"""Prompt 12, the three sections built on prompt 11 (contract §21.2, §21.3,
§21.10): "ask the hub" (F7), the weekly review with the advisor (M15) and the
digital CEO in prediction-only mode (OPERATING_MODEL §1.8).

Every table carries company_id (owner and holding rows: the holding's; a
workspace repository's corpus rows: its company's, so a CTO reads only its own
company's code; a prediction: its card's company, as it is sealed in the
proposer's own transaction) under FORCE RLS in the once-per-query form of 0009:

  knowledge.corpus_sources   one row per repository the corpus reads: the hub's
                             own (from disk, read-only) and each Code Workshop
                             workspace's (`not_indexed` when the hub cannot read it)
  knowledge.corpus_files     one row per file seen at the last build (its blob,
                             `indexed`, `secret` = left out entirely, `skipped`)
  knowledge.corpus_chunks    ~60-line passages with path, lines and commit; the
                             Persian-normalised text under pg_trgm and a 'simple'
                             tsvector (no embeddings, no vector store)
  knowledge.asks             AK-0001: the owner's question, the passages the code
                             retrieved (all the librarian may cite), the answer
  owner.reviews              WR-0001: one weekly review (agenda by code, <= 12)
  dceo.predictions           the digital CEO's sealed prediction of one card
                             (baseline and model), scored after the decision
  dceo.principles            DP-001: versioned principles (append-only rows)

The corpus is an index: its rows are replaced at each build (the worker may
delete them); every other new table has no delete. owner.settings gains the
blocks weekly_review and digital_ceo (§21.12). PR-121 (the digital CEO's
predictions sealed before the decision) becomes active (a new version, its
audit row) where it is still the seeded, paused version 1.

No decision kind is added (§21.12). The kind CHECK holds every kind of the
earlier migrations (0026 and 0026_1 re-add theirs NOT VALID; 0026_1
validates); this head validates it once more, so a round trip (test_hiring's
downgrade to 0009) ends with every card checked.

Revision ID: 0027_2
Revises: 0027_1
"""

from __future__ import annotations

import re

from hq_api.migration_sql import execute_script

revision = "0027_2"
down_revision = "0027_1"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
CORPUS = ("knowledge.corpus_sources", "knowledge.corpus_files", "knowledge.corpus_chunks")
TABLES = (
    *CORPUS,
    "knowledge.asks",
    "owner.reviews",
    "dceo.predictions",
    "dceo.principles",
)
APPEND_ONLY = ("dceo.principles",)
SEQUENCES = ("knowledge.ask_ref_seq", "owner.review_ref_seq", "dceo.principle_ref_seq")
PR121 = "PR-121"


def _rls(table: str) -> str:
    name = table.replace(".", "_")
    sql = f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
    """
    if table not in CORPUS:
        sql += f"""
        CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        """
    return sql


UPGRADE = r"""
CREATE SCHEMA dceo;
GRANT USAGE ON SCHEMA dceo TO @APP@;
CREATE SEQUENCE knowledge.ask_ref_seq;
CREATE SEQUENCE owner.review_ref_seq;
CREATE SEQUENCE dceo.principle_ref_seq;

-- ============================================================= corpus ==
CREATE TABLE knowledge.corpus_sources (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    key              text NOT NULL UNIQUE CHECK (key ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$'),
    kind             text NOT NULL CHECK (kind IN ('hub', 'workspace')),
    repo             text NOT NULL CHECK (length(repo) BETWEEN 1 AND 200),
    branch           text CHECK (length(branch) <= 200),
    commit           text CHECK (commit ~ '^[0-9a-f]{7,64}$'),
    state            text NOT NULL DEFAULT 'not_indexed'
                          CHECK (state IN ('indexed', 'not_indexed', 'failed')),
    state_reason     text CHECK (length(state_reason) <= 300),
    files            int NOT NULL DEFAULT 0 CHECK (files >= 0),
    chunks           int NOT NULL DEFAULT 0 CHECK (chunks >= 0),
    excluded_secret  int NOT NULL DEFAULT 0 CHECK (excluded_secret >= 0),
    skipped          int NOT NULL DEFAULT 0 CHECK (skipped >= 0),
    built_at         timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id)
);
CREATE TRIGGER corpus_sources_immutable BEFORE UPDATE ON knowledge.corpus_sources
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'key', 'kind', 'created_at');

CREATE TABLE knowledge.corpus_files (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    source_id   uuid NOT NULL,
    path        text NOT NULL CHECK (length(path) BETWEEN 1 AND 1000),
    blob_sha    text NOT NULL CHECK (blob_sha ~ '^[0-9a-f]{40,64}$'),
    size        int NOT NULL CHECK (size >= 0),
    kind        text NOT NULL CHECK (kind IN ('doc', 'code')),
    state       text NOT NULL CHECK (state IN ('indexed', 'secret', 'skipped')),
    reason      text CHECK (length(reason) <= 100),
    chunks      int NOT NULL DEFAULT 0 CHECK (chunks >= 0),
    commit      text NOT NULL CHECK (commit ~ '^[0-9a-f]{7,64}$'),
    indexed_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, path),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, source_id) REFERENCES knowledge.corpus_sources (company_id, id) ON DELETE CASCADE,
    CHECK (state = 'indexed' OR chunks = 0)
);

CREATE TABLE knowledge.corpus_chunks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id  uuid NOT NULL REFERENCES core.companies (id),
    file_id     uuid NOT NULL,
    source_id   uuid NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('doc', 'code')),
    repo        text NOT NULL CHECK (length(repo) BETWEEN 1 AND 200),
    path        text NOT NULL CHECK (length(path) BETWEEN 1 AND 1000),
    line_from   int NOT NULL CHECK (line_from >= 1),
    line_to     int NOT NULL,
    commit      text NOT NULL CHECK (commit ~ '^[0-9a-f]{7,64}$'),
    body        text NOT NULL CHECK (length(body) <= 20000),
    norm        text GENERATED ALWAYS AS (core.fa_normalize(body)) STORED,
    search      tsvector GENERATED ALWAYS AS (to_tsvector('simple', core.fa_normalize(body))) STORED,
    FOREIGN KEY (company_id, file_id) REFERENCES knowledge.corpus_files (company_id, id) ON DELETE CASCADE,
    CHECK (line_to >= line_from)
);
CREATE INDEX corpus_chunks_trgm ON knowledge.corpus_chunks USING gin (norm gin_trgm_ops);
CREATE INDEX corpus_chunks_search ON knowledge.corpus_chunks USING gin (search);
CREATE INDEX corpus_chunks_file ON knowledge.corpus_chunks (file_id);
CREATE TRIGGER corpus_chunks_append_only BEFORE UPDATE ON knowledge.corpus_chunks
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();

-- ================================================================ asks ==
CREATE TABLE knowledge.asks (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    ref                text NOT NULL UNIQUE
                            DEFAULT 'AK-' || lpad(nextval('knowledge.ask_ref_seq')::text, 4, '0')
                            CHECK (ref ~ '^AK-[0-9]{4,}$'),
    q                  text NOT NULL CHECK (length(q) BETWEEN 1 AND 500),
    scope              jsonb CHECK (scope IS NULL OR jsonb_typeof(scope) = 'object'),
    state              text NOT NULL DEFAULT 'queued'
                            CHECK (state IN ('queued', 'searching', 'answering', 'done', 'failed')),
    state_reason       text CHECK (length(state_reason) <= 300),
    found              int NOT NULL DEFAULT 0 CHECK (found BETWEEN 0 AND 100),
    passages           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(passages) = 'array'),
    suggestions        text[] NOT NULL DEFAULT '{}' CHECK (cardinality(suggestions) <= 10),
    answer_text        text CHECK (length(answer_text) <= 20000),  -- the API's answer_md
    citations          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(citations) = 'array'),
    citations_dropped  int NOT NULL DEFAULT 0 CHECK (citations_dropped >= 0),
    not_indexed        text[] NOT NULL DEFAULT '{}',
    usage_tokens       bigint NOT NULL DEFAULT 0 CHECK (usage_tokens >= 0),
    usage_usd          numeric(14, 6) NOT NULL DEFAULT 0 CHECK (usage_usd >= 0),
    work_id            uuid REFERENCES work.work (id),
    created_by_kind    text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
    created_by_code    text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz,
    CHECK (state NOT IN ('done', 'failed') OR finished_at IS NOT NULL)
);
CREATE INDEX asks_recent ON knowledge.asks (created_at DESC, id DESC);
CREATE UNIQUE INDEX asks_work ON knowledge.asks (work_id) WHERE work_id IS NOT NULL;
CREATE TRIGGER asks_immutable BEFORE UPDATE ON knowledge.asks
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'q', 'scope',
                                                      'created_by_kind', 'created_by_code', 'created_at');

-- ===================================================== weekly reviews ==
CREATE TABLE owner.reviews (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id             uuid NOT NULL REFERENCES core.companies (id),
    ref                    text NOT NULL UNIQUE
                                DEFAULT 'WR-' || lpad(nextval('owner.review_ref_seq')::text, 4, '0')
                                CHECK (ref ~ '^WR-[0-9]{4,}$'),
    week                   date NOT NULL UNIQUE CHECK (extract(isodow FROM week) = 6),  -- its Saturday
    scheduled_at           timestamptz NOT NULL,
    state                  text NOT NULL DEFAULT 'ready'
                                CHECK (state IN ('ready', 'in_progress', 'done', 'skipped')),
    agenda                 jsonb NOT NULL DEFAULT '[]'
                                CHECK (jsonb_typeof(agenda) = 'array' AND jsonb_array_length(agenda) <= 12),
    brief_work_id          uuid REFERENCES work.work (id),
    brief_message_ref      text CHECK (brief_message_ref ~ '^A-[0-9]+$'),
    minutes_deliverable_id uuid REFERENCES cartable.deliverables (id),
    minutes_ref            text CHECK (minutes_ref ~ '^O-[0-9]+$'),
    started_at             timestamptz,
    finished_at            timestamptz,
    duration_s             int CHECK (duration_s >= 0),
    skipped_at             timestamptz,
    version                int NOT NULL DEFAULT 1,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CHECK (state <> 'done' OR (finished_at IS NOT NULL AND minutes_ref IS NOT NULL)),
    CHECK (state <> 'skipped' OR skipped_at IS NOT NULL)
);
CREATE UNIQUE INDEX reviews_brief_work ON owner.reviews (brief_work_id) WHERE brief_work_id IS NOT NULL;
CREATE TRIGGER reviews_immutable BEFORE UPDATE ON owner.reviews
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'ref', 'week', 'created_at');
CREATE TRIGGER reviews_version BEFORE UPDATE ON owner.reviews
    FOR EACH ROW EXECUTE FUNCTION core.bump_version();

-- ===================================================== the digital CEO ==
-- A prediction is sealed when it is made (sealed_hash = sha256 of the
-- canonical JSON `sealed`); only the scoring columns change afterwards.
CREATE TABLE dceo.predictions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      uuid NOT NULL REFERENCES core.companies (id),
    decision_id     uuid NOT NULL REFERENCES cartable.decisions (id),
    decision_ref    text NOT NULL CHECK (decision_ref ~ '^D-[0-9]+$'),
    decision_kind   text NOT NULL CHECK (length(decision_kind) BETWEEN 1 AND 40),
    decision_title  text NOT NULL CHECK (length(decision_title) <= 300),
    decision_risk   text NOT NULL CHECK (decision_risk IN ('low', 'medium', 'high')),
    proposer_kind   text NOT NULL CHECK (proposer_kind IN ('owner', 'agent', 'service')),
    method          text NOT NULL CHECK (method IN ('baseline', 'model')),
    verdict         text NOT NULL CHECK (verdict IN ('approve', 'reject', 'return')),
    confidence      numeric(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    rationale_fa    text CHECK (length(rationale_fa) <= 300),
    principles      text[] NOT NULL DEFAULT '{}' CHECK (cardinality(principles) <= 10),
    basis           jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(basis) = 'object'),
    sealed          jsonb NOT NULL CHECK (jsonb_typeof(sealed) = 'object'),
    sealed_hash     text NOT NULL CHECK (sealed_hash ~ '^[0-9a-f]{64}$'),
    made_at         timestamptz NOT NULL DEFAULT now(),
    seen_before     boolean NOT NULL DEFAULT false,
    model           text CHECK (length(model) <= 80),
    usage_tokens    bigint NOT NULL DEFAULT 0 CHECK (usage_tokens >= 0),
    actual          text CHECK (actual IN ('approve', 'reject', 'return')),
    correct         boolean,
    decided_at      timestamptz,
    scored_at       timestamptz,
    UNIQUE (decision_id, method),
    CHECK ((actual IS NULL) = (correct IS NULL)),
    CHECK ((actual IS NULL) = (decided_at IS NULL)),
    CHECK (decided_at IS NULL OR made_at < decided_at)
);
CREATE INDEX predictions_made ON dceo.predictions (made_at DESC, id DESC);
CREATE INDEX predictions_decided ON dceo.predictions (decided_at DESC) WHERE decided_at IS NOT NULL;
CREATE TRIGGER predictions_sealed BEFORE UPDATE ON dceo.predictions
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'decision_id', 'decision_ref',
        'decision_kind', 'decision_title', 'decision_risk', 'proposer_kind', 'method', 'verdict',
        'confidence', 'rationale_fa', 'principles', 'basis', 'sealed', 'sealed_hash', 'made_at',
        'seen_before', 'model', 'usage_tokens');

CREATE TABLE dceo.principles (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id       uuid NOT NULL REFERENCES core.companies (id),
    ref              text NOT NULL CHECK (ref ~ '^DP-[0-9]{3,}$'),
    version          int NOT NULL CHECK (version >= 1),
    text_fa          text NOT NULL CHECK (length(text_fa) BETWEEN 1 AND 1000),
    sources          jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(sources) = 'array'),
    status           text NOT NULL CHECK (status IN ('proposed', 'active', 'retired')),
    edited_by_owner  boolean NOT NULL DEFAULT false,
    created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'service')),
    created_by_code  text NOT NULL CHECK (length(created_by_code) BETWEEN 1 AND 64),
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ref, version)
);
CREATE VIEW dceo.current_principles WITH (security_invoker = true) AS
    SELECT DISTINCT ON (ref) * FROM dceo.principles ORDER BY ref, version DESC;
GRANT SELECT ON dceo.current_principles TO @APP@;

-- The baseline's counts: the owner's past verdicts on cards of one kind, risk
-- and proposer kind over EVERY company (counts only, never a row), for the
-- proposer's own transaction, which sees its own company only.
CREATE FUNCTION dceo.owner_verdicts(p_kind text, p_risk text, p_proposer text, p_except uuid)
    RETURNS TABLE (status text, n bigint)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT d.status, count(*) FROM cartable.decisions d
    WHERE d.kind = p_kind AND d.risk = p_risk AND d.proposer_kind = p_proposer
      AND d.approver_code IS NULL AND d.decided_by_kind = 'owner'
      AND d.status IN ('approved', 'rejected', 'returned') AND d.id <> p_except
    GROUP BY d.status
$$;
REVOKE ALL ON FUNCTION dceo.owner_verdicts(text, text, text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION dceo.owner_verdicts(text, text, text, uuid) TO @APP@;

-- ====================================================== owner settings ==
ALTER TABLE owner.settings
    ADD COLUMN weekly_review jsonb NOT NULL
        DEFAULT '{"enabled": true, "day": "sa", "at": "10:00"}' CHECK (jsonb_typeof(weekly_review) = 'object'),
    ADD COLUMN digital_ceo jsonb NOT NULL
        DEFAULT '{"enabled": true, "reveal": "after", "model_predictions": true, "max_model_per_day": 20}'
        CHECK (jsonb_typeof(digital_ceo) = 'object');
GRANT UPDATE (weekly_review, digital_ceo) ON owner.settings TO hq_api;
"""

# PR-121 (prompt 12 §13): the seeded, paused version 1 gets a version 2,
# active. A fresh database has no PR-121 yet (the seed runs after the
# migrations); the seed then applies the same step (hq_api.domain.dceo.activate).
ACTIVATE_PR121 = f"""
WITH cur AS (
    SELECT * FROM oversight.current_protocols WHERE ref = '{PR121}'
), ins AS (
    INSERT INTO oversight.protocols (company_id, ref, version, title_fa, area, check_md, method, schedule,
                                     scope, evidence_md, severity, answerable, status, source,
                                     created_by_kind, created_by_code, calendar)
    SELECT company_id, ref, version + 1, title_fa, area, check_md, method, schedule, scope, evidence_md,
           severity, answerable, 'active', 'seed', 'service', 'migration-0027_2', calendar
    FROM cur WHERE version = 1 AND source = 'seed' AND status = 'paused'
    RETURNING company_id, ref, version
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', company_id, 'oversight.protocol_activate', 'A1', 'protocol',
       ref || '@' || version, false, 'prompt 12 §13: the digital CEO''s predictions (migration 0027_2)'
FROM ins;
"""


def upgrade() -> None:
    sql = UPGRADE.replace("@APP@", APP_ROLES)
    assert not re.search(r"@[A-Z_]+@", sql), "an unreplaced placeholder"
    execute_script(sql)
    grants = [_rls(t) for t in TABLES]
    grants += [
        f"""CREATE TRIGGER {t.replace(".", "_")}_append_only BEFORE UPDATE ON {t}
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();"""
        for t in APPEND_ONLY
    ]
    mutable = ", ".join(t for t in TABLES if t not in APPEND_ONLY and t != "knowledge.corpus_chunks")
    grants.append(f"GRANT SELECT, INSERT ON {', '.join(TABLES)} TO {APP_ROLES};")
    grants.append(f"GRANT UPDATE ON {mutable} TO {APP_ROLES};")
    # The corpus is an index: the nightly build (the worker) replaces its rows.
    grants.append(f"GRANT DELETE ON {', '.join(CORPUS)} TO {APP_ROLES};")
    grants.append(f"GRANT USAGE ON SEQUENCE {', '.join(SEQUENCES)} TO {APP_ROLES};")
    execute_script("\n".join(grants))
    execute_script(ACTIVATE_PR121)
    # Every kind of the earlier migrations is in the CHECK (none is new here):
    # the head validates every card against it.
    execute_script("ALTER TABLE cartable.decisions VALIDATE CONSTRAINT decisions_kind_check;")


def downgrade() -> None:
    execute_script(
        """
        -- The PR-121 versions stay (protocols are append-only).
        REVOKE UPDATE (weekly_review, digital_ceo) ON owner.settings FROM hq_api;
        ALTER TABLE owner.settings DROP COLUMN weekly_review, DROP COLUMN digital_ceo;
        DROP SCHEMA dceo CASCADE;
        DROP TABLE owner.reviews;
        DROP SEQUENCE owner.review_ref_seq;
        DROP TABLE knowledge.asks;
        DROP SEQUENCE knowledge.ask_ref_seq;
        DROP TABLE knowledge.corpus_chunks;
        DROP TABLE knowledge.corpus_files;
        DROP TABLE knowledge.corpus_sources;
        """
    )
