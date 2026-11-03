"""Prompt 21 part 1 (contract §29.1, §29.2, §29.6, §29.10, §29.14): routing by domain, the order report, the delegation budget, automatic hiring.

- §29.1 every notification, finding and decision card carries `domain`
  (business, media, revenue, product, tech, security, infra), `owner_visible`,
  `routed_to` (the handler's employee code) and `critical_reason` (data_leak,
  product_down, money, legal). Defaults (business, visible, no handler) keep
  every older writer working. owner.settings.destructive_owner_categories:
  the server_destructive categories that stay the owner's (default
  server_delete and db_drop; the rest go to the company's CTO).
- Data move, once (nothing is deleted): every technical notification and
  finding already there (domain tech, infra or security, by the same rules as
  hq_api.domain.routing) leaves the owner's lists (`owner_visible` false) for
  its handler's queue (`routed_to`: the company's CTO, else its SRE; the hub's
  platform SRE for the holding; the security analyst for the holding's
  security); one Audit row per kind moved. Every decision card gets its
  domain; a card someone else decides (a CEO's hire) is that one's.
- §29.2 owner.order_reports: one report per order of the owner (its state,
  acknowledgement, steps, blockers, outputs, end summary and the timers).
- §29.10 core.hiring.mode `auto`: hiring is open in mode auto (a CEO's hire
  inside the month envelope is approved by code; a working group's empty seat
  is filled by code). Set once now, with an Audit row.
- ops.watch_runs kind `tech_summary`: the weekly technical summary runs once
  a week (Saturday 09:00, the owner's time).

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

from hq_api.migration_sql import execute_script

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"
TENANT = "company_id = ANY ((SELECT core.allowed_company_ids())::uuid[])"
DOMAINS = "'business', 'media', 'revenue', 'product', 'tech', 'security', 'infra'"
CRITICAL = "'data_leak', 'product_down', 'money', 'legal'"
TECH = "'tech', 'security', 'infra'"
STATES = "'received', 'planned', 'in_progress', 'waiting', 'blocked', 'delivered', 'failed', 'cancelled'"
CATEGORIES = "'db_drop', 'volume_delete', 'backup_delete', 'disk_wipe', 'access_change', 'server_delete'"


def _routing_columns(table: str) -> str:
    return f"""
ALTER TABLE {table}
    ADD COLUMN domain          text NOT NULL DEFAULT 'business' CHECK (domain IN ({DOMAINS})),
    ADD COLUMN owner_visible   boolean NOT NULL DEFAULT true,
    ADD COLUMN routed_to       text CHECK (routed_to IS NULL OR length(routed_to) BETWEEN 1 AND 64),
    ADD COLUMN critical_reason text CHECK (critical_reason IS NULL OR critical_reason IN ({CRITICAL}));
"""


def _stale_on_change(skip: str) -> str:
    """advisor.stale_on_change (0027): a memo goes stale when its card changes;
    ⟨21⟩ the routing columns are bookkeeping, like the version."""
    return f"""
CREATE OR REPLACE FUNCTION advisor.stale_on_change() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
        skip text[] := ARRAY[{skip}];
    BEGIN
        IF NEW.version IS DISTINCT FROM OLD.version AND NEW.status = 'pending'
           AND (to_jsonb(NEW) - skip) IS DISTINCT FROM (to_jsonb(OLD) - skip) THEN
            UPDATE advisor.memos SET state = 'stale', state_reason = 'the card changed', updated_at = now()
             WHERE decision_id = NEW.id AND decision_version < NEW.version AND state <> 'stale';
        END IF;
        RETURN NEW;
    END $$;
"""


SCHEMA = f"""
{_stale_on_change("'version', 'updated_at', 'reminded_at', 'domain', 'owner_visible', 'routed_to', 'critical_reason'")}
{_routing_columns("notify.notifications")}
{_routing_columns("oversight.findings")}
{_routing_columns("cartable.decisions")}
CREATE INDEX notifications_owner_visible ON notify.notifications (created_at DESC)
    WHERE owner_visible;
CREATE INDEX findings_routed ON oversight.findings (routed_to, status) WHERE routed_to IS NOT NULL;
CREATE INDEX decisions_routed ON cartable.decisions (routed_to, status) WHERE routed_to IS NOT NULL;
GRANT UPDATE (owner_visible, routed_to) ON cartable.decisions TO hq_api;
GRANT UPDATE (owner_visible, routed_to) ON notify.notifications, oversight.findings TO {APP_ROLES};

ALTER TABLE owner.settings ADD COLUMN destructive_owner_categories text[] NOT NULL
    DEFAULT ARRAY['server_delete', 'db_drop']
    CHECK (destructive_owner_categories <@ ARRAY[{CATEGORIES}]);
GRANT UPDATE (destructive_owner_categories) ON owner.settings TO hq_api;

-- §29.10 automatic hiring
ALTER TABLE core.hiring DROP CONSTRAINT IF EXISTS hiring_mode_check;
ALTER TABLE core.hiring ADD CONSTRAINT hiring_mode_check
    CHECK (mode IN ('delegated', 'proposals', 'auto'));
ALTER TABLE core.hiring DROP CONSTRAINT IF EXISTS hiring_check;
ALTER TABLE core.hiring ADD CONSTRAINT hiring_check
    CHECK (state = 'closed' OR mode IN ('delegated', 'proposals', 'auto'));

-- §29.1 the weekly technical summary runs once a week
ALTER TABLE ops.watch_runs DROP CONSTRAINT IF EXISTS watch_runs_kind_check;
ALTER TABLE ops.watch_runs ADD CONSTRAINT watch_runs_kind_check
    CHECK (kind IN ('catalogue', 'growth_memo', 'holding_proposal', 'tech_summary'));

-- §29.2 the order report: one per order of the owner (the holding's row, as owner.orders)
CREATE TABLE owner.order_reports (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id         uuid NOT NULL REFERENCES core.companies (id),
    order_id           uuid NOT NULL UNIQUE REFERENCES owner.orders (id),
    ref                text NOT NULL UNIQUE CHECK (ref ~ '^F-[0-9]{{4,}}$'),
    state              text NOT NULL DEFAULT 'received' CHECK (state IN ({STATES})),
    ack                jsonb CHECK (ack IS NULL OR jsonb_typeof(ack) = 'object'),
    route              jsonb CHECK (route IS NULL OR jsonb_typeof(route) = 'object'),
    steps              jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(steps) = 'array'),
    blockers           jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(blockers) = 'array'),
    outputs            jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(outputs) = 'array'),
    summary            jsonb CHECK (summary IS NULL OR jsonb_typeof(summary) = 'object'),
    work_refs          text[] NOT NULL DEFAULT '{{}}',
    digest             text,
    acked_at           timestamptz,
    last_step_at       timestamptz,
    ack_nudged_at      timestamptz,
    progress_nudged_at timestamptz,
    owner_told_at      timestamptz,
    talk_stopped_at    timestamptz,
    ended_at           timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX order_reports_open ON owner.order_reports (created_at DESC) WHERE ended_at IS NULL;
CREATE INDEX order_reports_works ON owner.order_reports USING gin (work_refs);
CREATE TRIGGER order_reports_immutable BEFORE UPDATE ON owner.order_reports
    FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('id', 'company_id', 'order_id', 'ref', 'created_at');
CREATE TRIGGER order_reports_no_delete BEFORE DELETE ON owner.order_reports
    FOR EACH ROW EXECUTE FUNCTION core.reject_change();
ALTER TABLE owner.order_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE owner.order_reports FORCE ROW LEVEL SECURITY;
CREATE POLICY order_reports_tenant ON owner.order_reports TO {APP_ROLES} USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY order_reports_owner_role ON owner.order_reports TO hq USING (true) WITH CHECK (true);
GRANT SELECT, INSERT ON owner.order_reports TO {APP_ROLES};
GRANT UPDATE (state, ack, route, steps, blockers, outputs, summary, work_refs, digest, acked_at,
              last_step_at, ack_nudged_at, progress_nudged_at, owner_told_at, talk_stopped_at,
              ended_at, updated_at) ON owner.order_reports TO {APP_ROLES};
"""

# The same rules as hq_api.domain.routing (kept in step by the tests, which
# also run DATA_MOVE again on rows made the old way).
RULES = """
CREATE OR REPLACE FUNCTION pg_temp.finding_domain(p_ref text, p_area text, p_role text, p_kind text)
    RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_ref IN ('PR-060', 'PR-062') THEN 'infra'
        WHEN p_ref IN ('PR-013', 'PR-034', 'PR-142') THEN 'tech'
        WHEN p_ref IN ('PR-141', 'PR-043', 'PR-101', 'PR-102', 'PR-104') THEN 'product'
        WHEN p_ref = 'PR-103' THEN 'revenue'
        WHEN p_ref IS NULL AND p_kind = 'security' THEN 'security'
        WHEN p_ref IS NULL AND p_kind = 'app_health' THEN 'product'
        WHEN p_ref IS NULL AND p_kind = 'code' THEN 'tech'
        WHEN p_ref IS NULL AND p_kind IN ('growth', 'holding') THEN 'business'
        WHEN p_area IN ('security', 'safety') THEN 'security'
        WHEN p_role IN ('sre', 'hub_platform_sre') THEN 'infra'
        WHEN p_role IN ('cto', 'lead_developer', 'devops_engineer') THEN 'tech'
        WHEN p_role IN ('security_analyst', 'ai_safety') THEN 'security'
        WHEN p_area = 'data' THEN 'infra'
        WHEN p_area = 'product' THEN 'product'
        WHEN p_kind = 'security' THEN 'security'
        WHEN p_kind = 'app_health' THEN 'product'
        WHEN p_kind = 'code' THEN 'tech'
        ELSE 'business' END
$$;

CREATE OR REPLACE FUNCTION pg_temp.notification_domain(p_link text, p_source text) RETURNS text
    LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN p_link IN ('server_plan', 'founding') THEN 'business'
        WHEN p_link IN ('backup', 'audit', 'treasury') THEN 'infra'
        WHEN p_link IN ('code_session') THEN 'tech'
        WHEN p_link IN ('device', 'archive_fixity') THEN 'security'
        WHEN p_link IN ('support_queue', 'support_conversation', 'feedback') THEN 'product'
        WHEN p_link IN ('revenue_alert') THEN 'revenue'
        WHEN p_link LIKE 'media%' THEN 'media'
        WHEN p_source IN ('backup', 'llm-router', 'site-checks') THEN 'infra'
        WHEN p_source = 'archive-fixity' THEN 'security'
        WHEN p_link = 'deploy' THEN 'tech'
        WHEN p_link LIKE 'server!_%' ESCAPE '!' OR p_link IN ('backup', 'incident', 'catalogue')
             THEN 'infra'
        WHEN p_link IN ('security', 'secret', 'egress') THEN 'security'
        WHEN p_link IN ('revenue', 'funnel', 'referral') THEN 'revenue'
        WHEN p_link IN ('feedback', 'app_health') THEN 'product'
        ELSE 'business' END
$$;

-- who handles a technical item of a company: its CTO, else its SRE (the
-- holding: the platform SRE; the holding's security: its security analyst)
CREATE OR REPLACE FUNCTION pg_temp.handler(p_company uuid, p_domain text) RETURNS text
    LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN c.kind = 'holding' THEN
                (SELECT e.code FROM core.employees e
                  WHERE e.company_id = c.id AND e.status = 'active'
                    AND e.role IN ('security_analyst', 'hub_platform_sre', 'aiops_head')
                    AND (p_domain = 'security' OR e.role <> 'security_analyst')
                  ORDER BY CASE e.role WHEN 'security_analyst' THEN 0 WHEN 'hub_platform_sre' THEN 1
                                       ELSE 2 END, e.hired_at LIMIT 1)
           ELSE COALESCE(
                (SELECT e.code FROM core.employees e
                  WHERE e.company_id = c.id AND e.status = 'active' AND e.role IN ('cto', 'sre')
                  ORDER BY e.role = 'cto' DESC, e.hired_at LIMIT 1),
                (SELECT e.code FROM core.employees e
                  WHERE e.company_id = c.id AND e.status = 'active' AND e.kind = 'ceo'
                  ORDER BY e.hired_at LIMIT 1)) END
      FROM core.companies c WHERE c.id = p_company
$$;
"""

# The data move, once: technical findings and notifications to their handler's
# queue (one Audit row per kind), every card's domain, hiring open in mode auto.
DATA_MOVE = f"""
UPDATE oversight.findings f
   SET domain = pg_temp.finding_domain(p.ref, p.area, p.answerable, f.kind)
  FROM oversight.findings x LEFT JOIN oversight.protocols p ON p.id = x.protocol_id
 WHERE x.id = f.id;

WITH moved AS (
    UPDATE oversight.findings
       SET owner_visible = false, routed_to = pg_temp.handler(company_id, domain)
     WHERE domain IN ({TECH}) AND owner_visible
    RETURNING company_id
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', (SELECT id FROM core.companies WHERE kind = 'holding'),
       'routing.move', 'A1', 'findings', 'technical', false,
       format('prompt 21 (contract §29.1): %s technical findings moved to their handler''s queue '
              '(migration 0037; nothing deleted)', count(*))
FROM moved HAVING count(*) > 0;

UPDATE notify.notifications n
   SET domain = CASE WHEN n.link_kind = 'finding'
                     THEN COALESCE((SELECT f.domain FROM oversight.findings f WHERE f.ref = n.link_ref),
                                   'business')
                     ELSE pg_temp.notification_domain(n.link_kind, n.source_code) END;

WITH moved AS (
    UPDATE notify.notifications
       SET owner_visible = false, routed_to = pg_temp.handler(company_id, domain)
     WHERE domain IN ({TECH}) AND owner_visible
    RETURNING company_id
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', (SELECT id FROM core.companies WHERE kind = 'holding'),
       'routing.move', 'A1', 'notifications', 'technical', false,
       format('prompt 21 (contract §29.1): %s technical notifications moved to their handler''s queue '
              '(migration 0037; nothing deleted)', count(*))
FROM moved HAVING count(*) > 0;

WITH d AS (
    SELECT id, CASE
               WHEN kind IN ('server_destructive', 'server_plan') THEN 'infra'
               WHEN kind IN ('deploy', 'code_session', 'tool_enable') THEN 'tech'
               WHEN kind IN ('media_series', 'media_publish') THEN 'media'
               WHEN kind IN ('message_template', 'lifecycle_rule', 'support_go_live') THEN 'product'
               ELSE 'business' END AS domain
    FROM cartable.decisions
)
UPDATE cartable.decisions x
   SET domain = d.domain, owner_visible = x.approver_code IS NULL, routed_to = x.approver_code
  FROM d
 WHERE d.id = x.id AND (d.domain <> 'business' OR x.approver_code IS NOT NULL);

-- §29.10 hiring open in mode auto (the owner's decision, 2026-11-02)
INSERT INTO core.hiring (company_id) SELECT id FROM core.companies WHERE kind = 'holding'
    ON CONFLICT (company_id) DO NOTHING;
WITH opened AS (
    UPDATE core.hiring h SET state = 'open', mode = 'auto', changed_at = now(),
                             changed_by_kind = 'service', changed_by_code = 'prompt-21'
      FROM core.companies c
     WHERE c.id = h.company_id AND c.kind = 'holding'
       AND NOT (h.state = 'open' AND h.mode = 'auto')
    RETURNING h.company_id
)
INSERT INTO audit.entries (actor_kind, actor_code, principal_kind, company_id, action, action_class,
                           target_kind, target_ref, step_up, summary)
SELECT 'system', 'system', 'system', company_id, 'hiring.start', 'A2', 'hiring', 'auto', false,
       'prompt 21 (contract §29.10): hiring open in mode auto for every company (the owner''s decision, '
       || '2026-11-02; migration 0037)'
FROM opened;
"""

UPGRADE = SCHEMA + RULES + DATA_MOVE

DOWNGRADE = f"""
{_stale_on_change("'version', 'updated_at', 'reminded_at'")}
UPDATE core.hiring SET mode = 'proposals' WHERE mode = 'auto';
ALTER TABLE core.hiring DROP CONSTRAINT IF EXISTS hiring_check;
ALTER TABLE core.hiring ADD CONSTRAINT hiring_check
    CHECK (state = 'closed' OR mode IN ('delegated', 'proposals'));
ALTER TABLE core.hiring DROP CONSTRAINT IF EXISTS hiring_mode_check;
ALTER TABLE core.hiring ADD CONSTRAINT hiring_mode_check CHECK (mode IN ('delegated', 'proposals'));
DROP TABLE owner.order_reports;
ALTER TABLE ops.watch_runs DROP CONSTRAINT IF EXISTS watch_runs_kind_check;
DELETE FROM ops.watch_runs WHERE kind = 'tech_summary';
ALTER TABLE ops.watch_runs ADD CONSTRAINT watch_runs_kind_check
    CHECK (kind IN ('catalogue', 'growth_memo', 'holding_proposal'));
REVOKE UPDATE (destructive_owner_categories) ON owner.settings FROM hq_api;
ALTER TABLE owner.settings DROP COLUMN destructive_owner_categories;
REVOKE UPDATE (owner_visible, routed_to) ON notify.notifications, oversight.findings FROM {APP_ROLES};
REVOKE UPDATE (owner_visible, routed_to) ON cartable.decisions FROM hq_api;
ALTER TABLE cartable.decisions DROP COLUMN domain, DROP COLUMN owner_visible, DROP COLUMN routed_to,
    DROP COLUMN critical_reason;
ALTER TABLE oversight.findings DROP COLUMN domain, DROP COLUMN owner_visible, DROP COLUMN routed_to,
    DROP COLUMN critical_reason;
ALTER TABLE notify.notifications DROP COLUMN domain, DROP COLUMN owner_visible, DROP COLUMN routed_to,
    DROP COLUMN critical_reason;
"""


def upgrade() -> None:
    execute_script(UPGRADE)


def downgrade() -> None:
    execute_script(DOWNGRADE)
