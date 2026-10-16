"""Audit (contract §8) and control (§9).

audit.entries is append-only and hash-chained:
    hash = sha256(prev_hash || canonical_json(entry_without_hash))
canonical_json is audit.canonical(): a jsonb object of the entry's fields
(jsonb text output is deterministic: keys are sorted). A BEFORE INSERT
trigger (SECURITY DEFINER, owner hq) assigns seq/prev_hash/hash under the
chain head's row lock, so the chain is linear whatever the client does.
audit.verify_chain() recomputes every hash; the API role may only INSERT
and SELECT. The genesis prev_hash is 64 zeros.

control: one kill-switch row per company; the holding's row (kind
holding) stops every company. control.lock_state() answers "is this
company locked for agents, and why" across RLS (the holding row is
outside an agent's company scope), and is what llm-router uses too.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA audit;
        CREATE SCHEMA control;
        GRANT USAGE ON SCHEMA audit, control TO {APP_ROLES};
        GRANT USAGE ON SCHEMA control TO hq_llm_writer, hq_llm_reader;

        -- ------------------------------------------------------------ audit --
        CREATE TABLE audit.entries (
            seq             bigint PRIMARY KEY,
            at              timestamptz NOT NULL,
            actor_kind      text NOT NULL CHECK (actor_kind IN ('owner', 'agent', 'service', 'system')),
            actor_code      text NOT NULL CHECK (length(actor_code) BETWEEN 1 AND 64),
            principal_kind  text NOT NULL CHECK (principal_kind IN ('owner', 'agent', 'service', 'system')),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            action          text NOT NULL CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
            action_class    text NOT NULL CHECK (action_class IN ('A0', 'A1', 'A2', 'A3', 'A4')),
            target_kind     text NOT NULL CHECK (target_kind ~ '^[a-z_]{{2,30}}$'),
            target_ref      text NOT NULL CHECK (length(target_ref) BETWEEN 1 AND 200),
            request_id      text,
            ip_hash         text,
            step_up         boolean NOT NULL DEFAULT false,
            summary         text NOT NULL DEFAULT '' CHECK (length(summary) <= 500),
            prev_hash       text NOT NULL CHECK (prev_hash ~ '^[0-9a-f]{{64}}$'),
            hash            text NOT NULL CHECK (hash ~ '^[0-9a-f]{{64}}$')
        );
        CREATE INDEX entries_company_at ON audit.entries (company_id, at DESC);
        CREATE INDEX entries_actor ON audit.entries (actor_code, at DESC);

        CREATE TABLE audit.chain_head (
            id         int PRIMARY KEY CHECK (id = 1),
            last_seq   bigint NOT NULL,
            last_hash  text NOT NULL
        );
        INSERT INTO audit.chain_head VALUES (1, 0, repeat('0', 64));

        CREATE FUNCTION audit.canonical(e audit.entries) RETURNS text
            LANGUAGE sql IMMUTABLE AS $$
            SELECT jsonb_build_object(
                'seq', e.seq,
                'at', to_char(e.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                'actor_kind', e.actor_kind, 'actor_code', e.actor_code,
                'principal_kind', e.principal_kind, 'company_id', e.company_id,
                'action', e.action, 'action_class', e.action_class,
                'target_kind', e.target_kind, 'target_ref', e.target_ref,
                'request_id', e.request_id, 'ip_hash', e.ip_hash, 'step_up', e.step_up,
                'summary', e.summary, 'prev_hash', e.prev_hash)::text
            $$;

        CREATE FUNCTION audit.chain() RETURNS trigger
            LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                h audit.chain_head%ROWTYPE;
            BEGIN
                SELECT * INTO h FROM audit.chain_head WHERE id = 1 FOR UPDATE;
                NEW.seq := h.last_seq + 1;
                NEW.at := COALESCE(NEW.at, clock_timestamp());
                NEW.prev_hash := h.last_hash;
                NEW.hash := encode(sha256(convert_to(NEW.prev_hash || audit.canonical(NEW), 'UTF8')), 'hex');
                UPDATE audit.chain_head SET last_seq = NEW.seq, last_hash = NEW.hash WHERE id = 1;
                RETURN NEW;
            END $$;
        CREATE TRIGGER entries_chain BEFORE INSERT ON audit.entries
            FOR EACH ROW EXECUTE FUNCTION audit.chain();
        CREATE TRIGGER entries_append_only BEFORE UPDATE OR DELETE ON audit.entries
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER entries_no_truncate BEFORE TRUNCATE ON audit.entries
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER chain_head_no_delete BEFORE DELETE ON audit.chain_head
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- Verify the whole chain (all companies): first broken seq or NULL.
        CREATE FUNCTION audit.verify_chain(OUT ok boolean, OUT checked bigint, OUT first_bad_seq bigint)
            LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            DECLARE
                e audit.entries%ROWTYPE;
                prev text := repeat('0', 64);
                expect_seq bigint := 1;
            BEGIN
                ok := true;
                checked := 0;
                first_bad_seq := NULL;
                FOR e IN SELECT * FROM audit.entries ORDER BY seq LOOP
                    checked := checked + 1;
                    IF e.seq <> expect_seq OR e.prev_hash <> prev
                       OR e.hash <> encode(sha256(convert_to(e.prev_hash || audit.canonical(e), 'UTF8')), 'hex')
                    THEN
                        ok := false;
                        first_bad_seq := e.seq;
                        RETURN;
                    END IF;
                    prev := e.hash;
                    expect_seq := e.seq + 1;
                END LOOP;
                IF checked <> (SELECT last_seq FROM audit.chain_head WHERE id = 1)
                   OR prev <> (SELECT last_hash FROM audit.chain_head WHERE id = 1) THEN
                    ok := false;
                    first_bad_seq := expect_seq;
                END IF;
            END $$;

        GRANT SELECT, INSERT ON audit.entries TO {APP_ROLES};
        GRANT EXECUTE ON FUNCTION audit.verify_chain() TO {APP_ROLES};
        REVOKE ALL ON FUNCTION audit.chain() FROM PUBLIC;

        -- ---------------------------------------------------------- control --
        CREATE TABLE control.kill_switches (
            company_id       uuid PRIMARY KEY REFERENCES core.companies (id),
            state            text NOT NULL DEFAULT 'released' CHECK (state IN ('engaged', 'released')),
            reason           text CHECK (length(reason) <= 1000),
            changed_by_kind  text CHECK (changed_by_kind IN ('owner', 'agent', 'service', 'system')),
            changed_by_code  text,
            changed_at       timestamptz NOT NULL DEFAULT now(),
            version          int NOT NULL DEFAULT 1,
            updated_at       timestamptz NOT NULL DEFAULT now()
        );
        CREATE TRIGGER kill_switches_version BEFORE UPDATE ON control.kill_switches
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER kill_switches_no_delete BEFORE DELETE ON control.kill_switches
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        CREATE TABLE control.deploy_freezes (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            until            timestamptz NOT NULL,
            reason           text NOT NULL CHECK (length(reason) BETWEEN 1 AND 1000),
            created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code  text NOT NULL,
            created_at       timestamptz NOT NULL DEFAULT now(),
            lifted_at        timestamptz
        );
        CREATE INDEX deploy_freezes_active ON control.deploy_freezes (company_id, until)
            WHERE lifted_at IS NULL;

        -- 'holding' | 'company' | 'deploy_freeze' | NULL, for agents of p_company.
        CREATE FUNCTION control.lock_state(p_company uuid) RETURNS text
            LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
            SELECT CASE
                WHEN EXISTS (SELECT 1 FROM control.kill_switches k
                             JOIN core.companies c ON c.id = k.company_id
                             WHERE c.kind = 'holding' AND k.state = 'engaged') THEN 'holding'
                WHEN EXISTS (SELECT 1 FROM control.kill_switches k
                             WHERE k.company_id = p_company AND k.state = 'engaged') THEN 'company'
                WHEN EXISTS (SELECT 1 FROM control.deploy_freezes f
                             WHERE f.company_id = p_company AND f.lifted_at IS NULL
                               AND f.until > now()) THEN 'deploy_freeze'
            END
            $$;
        GRANT EXECUTE ON FUNCTION control.lock_state(uuid) TO {APP_ROLES}, hq_llm_writer, hq_llm_reader;

        GRANT SELECT, INSERT ON control.kill_switches, control.deploy_freezes TO {APP_ROLES};
        GRANT UPDATE (state, reason, changed_by_kind, changed_by_code, changed_at)
            ON control.kill_switches TO {APP_ROLES};
        GRANT UPDATE (lifted_at, until) ON control.deploy_freezes TO {APP_ROLES};
        """
    )
    execute_script(
        "\n".join(
            f"""
            ALTER TABLE {s}.{t} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {s}.{t} FORCE ROW LEVEL SECURITY;
            CREATE POLICY {t}_tenant ON {s}.{t} TO {APP_ROLES}
                USING (company_id = ANY (core.allowed_company_ids()))
                WITH CHECK (company_id = ANY (core.allowed_company_ids()));
            CREATE POLICY {t}_owner_role ON {s}.{t} TO hq USING (true) WITH CHECK (true);
            """
            for s, t in (
                ("audit", "entries"),
                ("control", "kill_switches"),
                ("control", "deploy_freezes"),
            )
        )
    )


def downgrade() -> None:
    execute_script("DROP SCHEMA control CASCADE; DROP SCHEMA audit CASCADE")
