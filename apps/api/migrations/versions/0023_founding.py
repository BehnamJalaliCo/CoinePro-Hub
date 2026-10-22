"""Prompt 09 §2-§4 (contract §18.8): company founding and server provisioning.

- core.foundings (C-0001): a company the holding founds from a repository or
  an idea; it belongs to the holding until its company exists.
- provisioning.plans (PV-0001): a server plan; `digest` is the sha256 of its
  canonical JSON (hq_common.provisioning), `sealed_digest` what the owner
  sealed. A plan whose digest differs from its seal never runs.
- provisioning.runs + run_events (append-only): the provisioner's steps,
  the one-time callback token (its sha256 only) and the new server's report.
- infra.servers: the servers the provisioner made (read-only in the API: no
  delete anywhere); infra.inventory: the latest listing of the Hetzner
  project (PR-063 compares it with the sealed plans).
- owner.settings.provision_ssh_sources: the owner's addresses SSH may come
  from (a plan never opens SSH to the whole internet).
- Decision kinds company_found and server_plan.

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
# The kinds after 0022 (0017_4 tool_enable, 0019 protocol, 0020 errand_action,
# 0021 lesson_adoption).
KINDS = (
    "'hire', 'dismissal', 'recurring_approval', 'deploy', 'a3_action', 'proposal', "
    "'budget_change', 'evaluation', 'code_session', 'tool_enable', 'protocol', 'errand_action', "
    "'lesson_adoption'"
)


def _rls(table: str) -> str:
    name = table.split(".")[1]
    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY {name}_tenant ON {table} TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
        CREATE POLICY {name}_owner_role ON {table} TO hq USING (true) WITH CHECK (true);
    """


def upgrade() -> None:
    execute_script(
        f"""
        CREATE SCHEMA IF NOT EXISTS provisioning;
        CREATE SCHEMA IF NOT EXISTS infra;
        GRANT USAGE ON SCHEMA provisioning, infra TO {APP_ROLES};

        -- ------------------------------------------------------- foundings --
        CREATE SEQUENCE core.founding_ref_seq;
        CREATE TABLE core.foundings (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref               text NOT NULL UNIQUE
                                   DEFAULT 'C-' || lpad(nextval('core.founding_ref_seq')::text, 4, '0'),
            -- The holding's until its company exists (then still the holding's:
            -- the founding is the holding's act; new_company_id points at it).
            company_id        uuid NOT NULL REFERENCES core.companies (id),
            source            jsonb NOT NULL CHECK (source->>'kind' IN ('repo', 'idea')),
            state             text NOT NULL DEFAULT 'auditing'
                                   CHECK (state IN ('auditing', 'proposed', 'sealed', 'provisioning',
                                                    'ready_for_login', 'active', 'cancelled')),
            name_fa           text CHECK (length(name_fa) <= 200),
            name_en           text CHECK (length(name_en) <= 200),
            code              text CHECK (code ~ '^[A-Z][A-Z0-9]{{1,9}}$'),
            audit             jsonb,
            proposal          jsonb,
            audit_work_id     uuid REFERENCES work.work (id),
            proposal_work_id  uuid REFERENCES work.work (id),
            workspace_code    text,
            grant_id          uuid REFERENCES workshop.grants (id),
            decision_id       uuid REFERENCES cartable.decisions (id),
            new_company_id    uuid REFERENCES core.companies (id),
            created_by_kind   text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code   text NOT NULL,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            activated_at      timestamptz,
            cancelled_at      timestamptz
        );
        CREATE INDEX foundings_state ON core.foundings (state, created_at);
        CREATE UNIQUE INDEX foundings_code_open ON core.foundings (code)
            WHERE code IS NOT NULL AND state <> 'cancelled';
        CREATE TRIGGER foundings_immutable BEFORE UPDATE ON core.foundings
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'company_id', 'source',
                                                              'created_by_kind', 'created_by_code',
                                                              'created_at');

        -- ----------------------------------------------------------- plans --
        CREATE SEQUENCE provisioning.plan_ref_seq;
        CREATE TABLE provisioning.plans (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            ref              text NOT NULL UNIQUE
                                  DEFAULT 'PV-' || lpad(nextval('provisioning.plan_ref_seq')::text, 4, '0'),
            company_id       uuid NOT NULL REFERENCES core.companies (id),
            company_code     text NOT NULL CHECK (company_code ~ '^[A-Z][A-Z0-9]{{1,9}}$'),
            founding_id      uuid REFERENCES core.foundings (id),
            name             text NOT NULL CHECK (length(name) BETWEEN 1 AND 63),
            type             text NOT NULL CHECK (length(type) BETWEEN 2 AND 10),
            location         text NOT NULL CHECK (length(location) BETWEEN 2 AND 10),
            image            text NOT NULL DEFAULT 'ubuntu-24.04',
            private_network  boolean NOT NULL DEFAULT false,
            firewall         jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(firewall) = 'array'),
            software         jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(software) = 'array'),
            work_user        text NOT NULL CHECK (length(work_user) BETWEEN 2 AND 32),
            repo             text CHECK (length(repo) <= 200),
            monthly_eur      numeric(12, 2) CHECK (monthly_eur >= 0),
            price            jsonb,  -- where the cost came from (Hetzner /pricing through the provisioner)
            digest           text NOT NULL CHECK (digest ~ '^[0-9a-f]{{64}}$'),
            state            text NOT NULL DEFAULT 'proposed'
                                  CHECK (state IN ('proposed', 'sealed', 'running', 'done', 'failed')),
            sealed_digest    text CHECK (sealed_digest ~ '^[0-9a-f]{{64}}$'),
            sealed_at        timestamptz,
            seal_step_up_id  uuid,
            decision_id      uuid REFERENCES cartable.decisions (id),
            version          int NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_by_kind  text NOT NULL CHECK (created_by_kind IN ('owner', 'agent', 'service')),
            created_by_code  text NOT NULL,
            created_at       timestamptz NOT NULL DEFAULT now(),
            updated_at       timestamptz NOT NULL DEFAULT now(),
            CHECK ((state = 'proposed') = (sealed_digest IS NULL))
        );
        CREATE INDEX plans_state ON provisioning.plans (state, sealed_at);
        CREATE INDEX plans_founding ON provisioning.plans (founding_id);
        CREATE TRIGGER plans_immutable BEFORE UPDATE ON provisioning.plans
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'ref', 'founding_id',
                                                              'created_by_kind', 'created_by_code',
                                                              'created_at');

        -- ------------------------------------------------------------ runs --
        CREATE TABLE provisioning.runs (
            id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id              uuid NOT NULL REFERENCES provisioning.plans (id),
            company_id           uuid NOT NULL REFERENCES core.companies (id),
            state                text NOT NULL DEFAULT 'running'
                                      CHECK (state IN ('queued', 'running', 'done', 'failed')),
            sealed_digest        text NOT NULL CHECK (sealed_digest ~ '^[0-9a-f]{{64}}$'),
            steps                jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(steps) = 'array'),
            server               jsonb,
            login                jsonb,
            error                jsonb,
            callback_sha256      text CHECK (callback_sha256 ~ '^[0-9a-f]{{64}}$'),
            callback_expires_at  timestamptz,
            callback_used_at     timestamptz,
            cloud_init           jsonb,
            last_seq             int NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
            created_at           timestamptz NOT NULL DEFAULT now(),
            updated_at           timestamptz NOT NULL DEFAULT now(),
            finished_at          timestamptz
        );
        CREATE UNIQUE INDEX runs_plan_open ON provisioning.runs (plan_id)
            WHERE state IN ('queued', 'running');
        CREATE UNIQUE INDEX runs_callback ON provisioning.runs (callback_sha256)
            WHERE callback_sha256 IS NOT NULL;
        CREATE TRIGGER runs_immutable BEFORE UPDATE ON provisioning.runs
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'plan_id', 'company_id',
                                                              'sealed_digest', 'created_at');

        CREATE TABLE provisioning.run_events (
            run_id      uuid NOT NULL REFERENCES provisioning.runs (id),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            seq         int NOT NULL CHECK (seq >= 1),
            at          timestamptz NOT NULL DEFAULT now(),
            key         text NOT NULL CHECK (length(key) <= 40),
            state       text NOT NULL CHECK (state IN ('pending', 'running', 'done', 'failed', 'queued')),
            log_tail    jsonb NOT NULL DEFAULT '[]',
            PRIMARY KEY (run_id, seq)
        );
        CREATE TRIGGER run_events_append_only BEFORE UPDATE OR DELETE ON provisioning.run_events
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- ----------------------------------------------------------- infra --
        CREATE TABLE infra.servers (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            plan_id      uuid NOT NULL REFERENCES provisioning.plans (id),
            run_id       uuid REFERENCES provisioning.runs (id),
            hetzner_id   bigint NOT NULL UNIQUE,
            name         text NOT NULL CHECK (length(name) <= 63),
            ipv4         text CHECK (length(ipv4) <= 45),
            ipv6         text CHECK (length(ipv6) <= 64),
            private_ip   text CHECK (length(private_ip) <= 45),
            labels       jsonb NOT NULL DEFAULT '{{}}',
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now()
        );
        CREATE TRIGGER servers_immutable BEFORE UPDATE ON infra.servers
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'plan_id',
                                                              'hetzner_id', 'created_at');
        CREATE TRIGGER servers_no_delete BEFORE DELETE ON infra.servers
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        -- The latest listing of the Hetzner project (the holding's record).
        CREATE TABLE infra.inventory (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            fetched_at  timestamptz NOT NULL DEFAULT now(),
            ok          boolean NOT NULL,
            error       text CHECK (length(error) <= 300),
            servers     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(servers) = 'array')
        );
        CREATE INDEX inventory_latest ON infra.inventory (fetched_at DESC);
        CREATE TRIGGER inventory_append_only BEFORE UPDATE OR DELETE ON infra.inventory
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();

        {_rls("core.foundings")}
        {_rls("provisioning.plans")}
        {_rls("provisioning.runs")}
        {_rls("provisioning.run_events")}
        {_rls("infra.servers")}
        {_rls("infra.inventory")}

        GRANT SELECT, INSERT ON core.foundings, provisioning.plans, provisioning.runs,
            provisioning.run_events, infra.servers, infra.inventory TO {APP_ROLES};
        GRANT USAGE ON SEQUENCE core.founding_ref_seq, provisioning.plan_ref_seq TO {APP_ROLES};
        GRANT UPDATE (state, name_fa, name_en, code, audit, proposal, audit_work_id, proposal_work_id,
                      workspace_code, grant_id, decision_id, new_company_id, updated_at, activated_at,
                      cancelled_at)
            ON core.foundings TO {APP_ROLES};
        GRANT UPDATE (company_id, company_code, name, type, location, image, private_network, firewall,
                      software, work_user, repo, monthly_eur, price, digest, state, sealed_digest,
                      sealed_at, seal_step_up_id, decision_id, version, updated_at)
            ON provisioning.plans TO {APP_ROLES};
        GRANT UPDATE (state, steps, server, login, error, callback_sha256, callback_expires_at,
                      callback_used_at, cloud_init, last_seq, updated_at, finished_at)
            ON provisioning.runs TO {APP_ROLES};
        GRANT UPDATE (name, ipv4, ipv6, private_ip, labels, run_id, updated_at)
            ON infra.servers TO {APP_ROLES};

        ALTER TABLE owner.settings ADD COLUMN provision_ssh_sources text[] NOT NULL DEFAULT '{{}}'
            CHECK (cardinality(provision_ssh_sources) <= 20);
        GRANT UPDATE (provision_ssh_sources) ON owner.settings TO hq_api;

        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS}, 'company_found', 'server_plan')) NOT VALID;  -- 0025 validates
        """
    )


def downgrade() -> None:
    execute_script(
        f"""
        -- NOT VALID: past founding and plan cards stay (resolutions point at them).
        ALTER TABLE cartable.decisions DROP CONSTRAINT decisions_kind_check;
        ALTER TABLE cartable.decisions ADD CONSTRAINT decisions_kind_check
            CHECK (kind IN ({KINDS})) NOT VALID;
        ALTER TABLE owner.settings DROP COLUMN provision_ssh_sources;
        DROP TABLE infra.inventory;
        DROP TABLE infra.servers;
        DROP TABLE provisioning.run_events;
        DROP TABLE provisioning.runs;
        DROP TABLE provisioning.plans;
        DROP SEQUENCE provisioning.plan_ref_seq;
        DROP TABLE core.foundings;
        DROP SEQUENCE core.founding_ref_seq;
        DROP SCHEMA infra;
        DROP SCHEMA provisioning;
        """
    )
