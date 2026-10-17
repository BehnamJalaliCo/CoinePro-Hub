"""The three inboxes (contract §5): decisions, deliverables and ratings,
the resolutions ledger, message threads, and file metadata.

Append-only (UPDATE/DELETE/TRUNCATE rejected for everyone): deliverables,
ratings (each re-rating is a new version), resolutions, messages, files.
Resolutions are numbered M-0001.. in one gapless holding-wide sequence;
messages are numbered per thread (<thread code>-<seq>, e.g. A-0142).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
APPEND_ONLY = [
    ("cartable", "deliverables"),
    ("cartable", "ratings"),
    ("cartable", "resolutions"),
    ("msg", "messages"),
    ("files", "files"),
]
TENANT = [
    ("cartable", "decisions"),
    ("cartable", "deliverables"),
    ("cartable", "ratings"),
    ("cartable", "resolutions"),
    ("msg", "threads"),
    ("msg", "messages"),
    ("files", "files"),
]


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA cartable;
        CREATE SCHEMA msg;
        CREATE SCHEMA files;
        GRANT USAGE ON SCHEMA cartable, msg, files TO {APP_ROLES};

        -- ------------------------------------------------------------ files --
        CREATE TABLE files.files (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            name             text NOT NULL CHECK (length(name) BETWEEN 1 AND 255),
            mime             text NOT NULL CHECK (mime ~ '^[a-z0-9.+-]+/[a-z0-9.+-]+$'),
            size             bigint NOT NULL CHECK (size BETWEEN 0 AND 104857600),
            sha256           text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
            storage_key      text NOT NULL UNIQUE,
            created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code  text NOT NULL,
            created_at       timestamptz NOT NULL DEFAULT now()
        );

        -- -------------------------------------------------------- decisions --
        CREATE SEQUENCE cartable.decision_ref_seq;
        CREATE SEQUENCE cartable.deliverable_ref_seq;
        GRANT USAGE ON SEQUENCE cartable.decision_ref_seq, cartable.deliverable_ref_seq TO {APP_ROLES};

        CREATE TABLE cartable.decisions (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref                   text NOT NULL UNIQUE
                                       DEFAULT 'D-' || lpad(nextval('cartable.decision_ref_seq')::text, 6, '0'),
            company_id            uuid NOT NULL REFERENCES core.companies (id),
            kind                  text NOT NULL
                                       CHECK (kind IN ('hire', 'dismissal', 'recurring_approval', 'deploy',
                                                       'a3_action', 'proposal', 'budget_change',
                                                       'evaluation')),
            action_class          text NOT NULL CHECK (action_class IN ('A1', 'A2', 'A3')),
            title                 text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            what                  text NOT NULL DEFAULT '' CHECK (length(what) <= 20000),
            why                   text NOT NULL DEFAULT '' CHECK (length(why) <= 20000),
            proposer_kind         text NOT NULL CHECK (proposer_kind IN ('owner', 'agent', 'service')),
            proposer_code         text NOT NULL,
            work_id               uuid REFERENCES work.work (id),
            quota_tokens          bigint CHECK (quota_tokens >= 0),
            quota_usd             numeric(14, 6) CHECK (quota_usd >= 0),
            risk                  text NOT NULL DEFAULT 'low' CHECK (risk IN ('low', 'medium', 'high')),
            risk_note             text CHECK (length(risk_note) <= 2000),
            reversible            boolean NOT NULL DEFAULT true,
            payload               jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(payload) = 'object'),
            status                text NOT NULL DEFAULT 'pending'
                                       CHECK (status IN ('pending', 'approved', 'rejected', 'returned',
                                                         'expired', 'withdrawn')),
            expires_at            timestamptz,
            decided_at            timestamptz,
            decided_by_kind       text CHECK (decided_by_kind IN ('owner', 'agent', 'service')),
            decided_by_code       text,
            seal_at               timestamptz,
            seal_method           text CHECK (seal_method IN ('passkey_uv')),
            seal_step_up_id       uuid,
            note                  text CHECK (length(note) <= 5000),
            reason_code           text CHECK (reason_code IN ('cost', 'risk', 'timing', 'quality', 'other')),
            amendments            jsonb,
            resolution_id         uuid,
            thread_code           text,
            effect_status         text NOT NULL DEFAULT 'none'
                                       CHECK (effect_status IN ('none', 'pending', 'applied', 'failed')),
            effect_error          text,
            effect_applied_at     timestamptz,
            reminded_at           timestamptz,
            version               int NOT NULL DEFAULT 1,
            created_at            timestamptz NOT NULL DEFAULT now(),
            updated_at            timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'pending') = (decided_at IS NULL) OR status = 'expired')
        );
        CREATE INDEX decisions_pending ON cartable.decisions (company_id, created_at)
            WHERE status = 'pending';
        CREATE INDEX decisions_company ON cartable.decisions (company_id, created_at DESC);

        -- Once decided, a decision's verdict never changes (HQS01).
        CREATE FUNCTION cartable.decisions_final() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.status <> 'pending' AND NEW.status <> OLD.status THEN
                    RAISE EXCEPTION 'decision % is already %', OLD.ref, OLD.status
                        USING ERRCODE = 'HQS01';
                END IF;
                RETURN NEW;
            END $$;
        CREATE TRIGGER decisions_final BEFORE UPDATE OF status ON cartable.decisions
            FOR EACH ROW EXECUTE FUNCTION cartable.decisions_final();
        CREATE TRIGGER decisions_immutable BEFORE UPDATE ON cartable.decisions
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'ref', 'company_id', 'kind', 'action_class', 'title', 'what', 'why',
                'proposer_kind', 'proposer_code', 'work_id', 'quota_tokens', 'quota_usd',
                'risk', 'risk_note', 'reversible', 'payload', 'created_at');
        CREATE TRIGGER decisions_version BEFORE UPDATE ON cartable.decisions
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        ALTER TABLE core.employees ADD CONSTRAINT employees_hired_by_decision
            FOREIGN KEY (hired_by_decision_id) REFERENCES cartable.decisions (id);
        ALTER TABLE work.escrows ADD CONSTRAINT escrows_decision
            FOREIGN KEY (decision_id) REFERENCES cartable.decisions (id);

        -- ----------------------------------------------------- deliverables --
        CREATE TABLE cartable.deliverables (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref            text NOT NULL UNIQUE
                                DEFAULT 'O-' || lpad(nextval('cartable.deliverable_ref_seq')::text, 6, '0'),
            company_id     uuid NOT NULL REFERENCES core.companies (id),
            work_id        uuid NOT NULL REFERENCES work.work (id),
            producer_id    uuid NOT NULL REFERENCES core.employees (id),
            title          text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            summary        text NOT NULL DEFAULT '' CHECK (length(summary) <= 5000),
            body           text CHECK (length(body) <= 500000),
            attachments    uuid[] NOT NULL DEFAULT '{{}}',
            produced_with  jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(produced_with) = 'object'),
            usage          jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(usage) = 'object'),
            evidence       jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(evidence) = 'array'),
            created_at     timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX deliverables_company ON cartable.deliverables (company_id, created_at DESC);
        CREATE INDEX deliverables_producer ON cartable.deliverables (producer_id, created_at DESC);
        CREATE INDEX deliverables_work ON cartable.deliverables (work_id);

        -- Owner ratings 1..10 with history: every re-rating is a new row.
        CREATE TABLE cartable.ratings (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            deliverable_id  uuid NOT NULL REFERENCES cartable.deliverables (id),
            version_no      int  NOT NULL CHECK (version_no >= 1),
            score           int  NOT NULL CHECK (score BETWEEN 1 AND 10),
            comment         text CHECK (length(comment) <= 5000),
            rated_by_code   text NOT NULL,
            rated_at        timestamptz NOT NULL DEFAULT now(),
            UNIQUE (deliverable_id, version_no)
        );

        -- ------------------------------------------------------- resolutions --
        CREATE TABLE cartable.resolutions (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref                text NOT NULL UNIQUE CHECK (ref ~ '^M-[0-9]{{4,}}$'),
            company_id         uuid NOT NULL REFERENCES core.companies (id),
            title              text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
            body               text NOT NULL DEFAULT '' CHECK (length(body) <= 50000),
            source_decision_id uuid REFERENCES cartable.decisions (id),
            source_message_id  uuid,
            sealed_by_kind     text NOT NULL CHECK (sealed_by_kind IN ('owner', 'agent')),
            sealed_by_code     text NOT NULL,
            sealed_at          timestamptz NOT NULL DEFAULT now(),
            sent_to            text[] NOT NULL DEFAULT '{{}}',
            follow_up_work_id  uuid REFERENCES work.work (id),
            created_at         timestamptz NOT NULL DEFAULT now()
        );
        -- M-0001: one gapless holding-wide sequence (core.counters 'resolution').
        CREATE FUNCTION cartable.next_resolution_ref() RETURNS text
            LANGUAGE sql AS $$
            SELECT 'M-' || lpad(n::text, greatest(4, length(n::text)), '0')
            FROM core.next_counter('resolution') AS n
            $$;
        GRANT EXECUTE ON FUNCTION cartable.next_resolution_ref() TO {APP_ROLES};
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_resolution
            FOREIGN KEY (resolution_id) REFERENCES cartable.resolutions (id);

        -- ---------------------------------------------------------- messages --
        CREATE TABLE msg.threads (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            code             text NOT NULL UNIQUE CHECK (code ~ '^(A|[A-Z][A-Z0-9]{{1,9}}(-[A-Z0-9]+){{1,2}})$'),
            kind             text NOT NULL
                                  CHECK (kind IN ('advisor', 'ceo', 'manager', 'department', 'employee')),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            department_id    uuid,
            employee_id      uuid REFERENCES core.employees (id),
            title_fa         text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 200),
            last_seq         int  NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
            last_message_at  timestamptz,
            owner_read_seq   int  NOT NULL DEFAULT 0 CHECK (owner_read_seq >= 0),
            created_at       timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (company_id, department_id) REFERENCES core.departments (company_id, id),
            CHECK (owner_read_seq <= last_seq)
        );
        CREATE TRIGGER threads_immutable BEFORE UPDATE ON msg.threads
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'code', 'kind', 'company_id', 'department_id', 'employee_id', 'created_at');
        CREATE TRIGGER threads_seq_forward BEFORE UPDATE ON msg.threads
            FOR EACH ROW WHEN (NEW.last_seq < OLD.last_seq) EXECUTE FUNCTION core.reject_change();

        CREATE TABLE msg.messages (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id    uuid NOT NULL REFERENCES msg.threads (id),
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            seq          int  NOT NULL CHECK (seq >= 1),
            ref          text NOT NULL UNIQUE,
            author_kind  text NOT NULL CHECK (author_kind IN ('owner', 'agent', 'service')),
            author_code  text NOT NULL,
            body         text NOT NULL CHECK (length(body) BETWEEN 1 AND 100000),
            attachments  uuid[] NOT NULL DEFAULT '{{}}',
            links        jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(links) = 'object'),
            kind         text NOT NULL DEFAULT 'text' CHECK (kind IN ('text', 'voice_transcript', 'system')),
            created_at   timestamptz NOT NULL DEFAULT now(),
            search       tsvector GENERATED ALWAYS AS (to_tsvector('simple', core.fa_normalize(body))) STORED,
            UNIQUE (thread_id, seq)
        );
        CREATE INDEX messages_thread_seq ON msg.messages (thread_id, seq);
        CREATE INDEX messages_search ON msg.messages USING gin (search);
        CREATE INDEX messages_trgm ON msg.messages USING gin (core.fa_normalize(body) gin_trgm_ops);
        ALTER TABLE cartable.resolutions ADD CONSTRAINT resolutions_source_message
            FOREIGN KEY (source_message_id) REFERENCES msg.messages (id);

        -- Posting allocates the next per-thread number under the thread's row lock.
        CREATE FUNCTION msg.post(p_thread uuid, p_author_kind text, p_author_code text, p_body text,
                                 p_links jsonb, p_attachments uuid[], p_kind text)
            RETURNS msg.messages
            LANGUAGE plpgsql AS $$
            DECLARE
                t msg.threads%ROWTYPE;
                m msg.messages%ROWTYPE;
            BEGIN
                UPDATE msg.threads SET last_seq = last_seq + 1, last_message_at = now(),
                       owner_read_seq = CASE WHEN p_author_kind = 'owner' THEN last_seq + 1
                                             ELSE owner_read_seq END
                 WHERE id = p_thread RETURNING * INTO t;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'thread not found' USING ERRCODE = 'HQN01';
                END IF;
                INSERT INTO msg.messages (thread_id, company_id, seq, ref, author_kind, author_code,
                                          body, attachments, links, kind)
                VALUES (t.id, t.company_id, t.last_seq,
                        t.code || '-' || lpad(t.last_seq::text, greatest(4, length(t.last_seq::text)), '0'),
                        p_author_kind, p_author_code, p_body, COALESCE(p_attachments, '{{}}'),
                        COALESCE(p_links, '{{}}'), COALESCE(p_kind, 'text'))
                RETURNING * INTO m;
                RETURN m;
            END $$;
        GRANT EXECUTE ON FUNCTION msg.post(uuid, text, text, text, jsonb, uuid[], text) TO {APP_ROLES};

        -- ------------------------------------------------------------- grants --
        GRANT SELECT, INSERT ON cartable.decisions, cartable.deliverables, cartable.ratings,
            cartable.resolutions, msg.threads, msg.messages, files.files TO {APP_ROLES};
        GRANT UPDATE (status, expires_at, decided_at, decided_by_kind, decided_by_code, seal_at,
                      seal_method, seal_step_up_id, note, reason_code, amendments, resolution_id,
                      thread_code, effect_status, effect_error, effect_applied_at, reminded_at)
            ON cartable.decisions TO {APP_ROLES};
        GRANT UPDATE (last_seq, last_message_at, owner_read_seq) ON msg.threads TO {APP_ROLES};
        """
    )
    execute_script(
        "\n".join(
            f"""
            CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {s}.{t}
                FOR EACH ROW EXECUTE FUNCTION core.reject_change();
            CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {s}.{t}
                FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();
            """
            for s, t in APPEND_ONLY
        )
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
            for s, t in TENANT
        )
    )


def downgrade() -> None:
    execute_script(
        """
        ALTER TABLE core.employees DROP CONSTRAINT employees_hired_by_decision;
        ALTER TABLE work.escrows DROP CONSTRAINT escrows_decision;
        DROP SCHEMA msg CASCADE;
        DROP SCHEMA cartable CASCADE;
        DROP SCHEMA files CASCADE;
        """
    )
