"""Notifications and Khalvat (contract §6), owner identity (§2) and the
owner's presence, settings and interaction log (§1.8).

auth.*: passkeys (public keys only), sessions and step-up/enrolment tokens
are stored as SHA-256 digests, never in clear. One owner (single human).
owner.interactions is append-only: the raw material of the digital CEO.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from hq_api.migration_sql import execute_script

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP_ROLES = "hq_api, hq_worker"


def upgrade() -> None:
    execute_script(
        rf"""
        CREATE SCHEMA notify;
        CREATE SCHEMA auth;
        CREATE SCHEMA owner;
        GRANT USAGE ON SCHEMA notify, owner TO {APP_ROLES};
        GRANT USAGE ON SCHEMA auth TO hq_api, hq_worker;

        -- ------------------------------------------------------ notifications --
        CREATE TABLE notify.notifications (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      uuid NOT NULL REFERENCES core.companies (id),
            level           text NOT NULL
                                 CHECK (level IN ('urgent', 'decision', 'report', 'info', 'learning')),
            title_fa        text NOT NULL CHECK (length(title_fa) BETWEEN 1 AND 300),
            body_fa         text NOT NULL DEFAULT '' CHECK (length(body_fa) <= 4000),
            link_kind       text CHECK (link_kind ~ '^[a-z_]{{2,30}}$'),
            link_ref        text CHECK (length(link_ref) <= 100),
            source_kind     text NOT NULL CHECK (source_kind IN ('owner', 'agent', 'service', 'system')),
            source_code     text NOT NULL,
            choices         jsonb CHECK (choices IS NULL OR jsonb_typeof(choices) = 'array'),
            answer          text,
            answered_at     timestamptz,
            state           text NOT NULL DEFAULT 'delivered'
                                 CHECK (state IN ('delivered', 'queued', 'held', 'suppressed')),
            queue_reason    text CHECK (queue_reason IN ('digest', 'khalvat', 'attention_quota',
                                                         'rhythm', 'muted', 'learning_cap')),
            delivered_in_app   boolean NOT NULL DEFAULT false,
            delivered_web_push boolean NOT NULL DEFAULT false,
            delivered_fcm      boolean NOT NULL DEFAULT false,
            delivered_telegram boolean NOT NULL DEFAULT false,
            sound           boolean NOT NULL DEFAULT false,
            delivered_at    timestamptz,
            batch_id        uuid,
            read_at         timestamptz,
            created_at      timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX notifications_unread ON notify.notifications (company_id, level, created_at DESC)
            WHERE read_at IS NULL;
        CREATE INDEX notifications_created ON notify.notifications (created_at DESC);
        CREATE INDEX notifications_queued ON notify.notifications (created_at)
            WHERE state IN ('queued', 'held');
        CREATE TRIGGER notifications_immutable BEFORE UPDATE ON notify.notifications
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable(
                'id', 'company_id', 'level', 'title_fa', 'body_fa', 'link_kind', 'link_ref',
                'source_kind', 'source_code', 'choices', 'created_at');

        -- Owner-level matrix {{"*"|code: {{level: {{in_app, push, sound, muted_until}}}}}}.
        CREATE TABLE notify.settings (
            id          int PRIMARY KEY CHECK (id = 1),
            matrix      jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(matrix) = 'object'),
            version     int NOT NULL DEFAULT 1,
            updated_at  timestamptz NOT NULL DEFAULT now()
        );
        INSERT INTO notify.settings (id) VALUES (1);
        CREATE TRIGGER settings_version BEFORE UPDATE ON notify.settings
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        CREATE TABLE notify.web_push_subscriptions (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            endpoint         text NOT NULL UNIQUE CHECK (endpoint ~ '^https://'),
            p256dh           text NOT NULL,
            auth             text NOT NULL,
            device_name      text NOT NULL CHECK (length(device_name) BETWEEN 1 AND 100),
            failures         int NOT NULL DEFAULT 0,
            last_success_at  timestamptz,
            created_at       timestamptz NOT NULL DEFAULT now(),
            revoked_at       timestamptz
        );
        CREATE TABLE notify.fcm_tokens (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token        text NOT NULL UNIQUE CHECK (length(token) BETWEEN 20 AND 4096),
            device_name  text NOT NULL CHECK (length(device_name) BETWEEN 1 AND 100),
            failures     int NOT NULL DEFAULT 0,
            created_at   timestamptz NOT NULL DEFAULT now(),
            revoked_at   timestamptz
        );

        -- Digest batches: one push per batch (§6 "decision" level).
        CREATE TABLE notify.digest_batches (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES core.companies (id),
            items       int NOT NULL CHECK (items >= 1),
            reason      text NOT NULL,
            sent_at     timestamptz NOT NULL DEFAULT now()
        );

        GRANT SELECT, INSERT ON notify.notifications, notify.digest_batches TO {APP_ROLES};
        GRANT UPDATE (answer, answered_at, state, queue_reason, delivered_in_app,
                      delivered_web_push, delivered_fcm, delivered_telegram, sound, delivered_at,
                      batch_id, read_at)
            ON notify.notifications TO {APP_ROLES};
        GRANT SELECT, UPDATE (matrix) ON notify.settings TO {APP_ROLES};
        GRANT SELECT, INSERT ON notify.web_push_subscriptions, notify.fcm_tokens TO {APP_ROLES};
        GRANT UPDATE (failures, last_success_at, revoked_at) ON notify.web_push_subscriptions
            TO {APP_ROLES};
        GRANT UPDATE (failures, revoked_at) ON notify.fcm_tokens TO {APP_ROLES};

        -- ------------------------------------------------------------- auth --
        CREATE TABLE auth.passkeys (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            credential_id    bytea NOT NULL UNIQUE,
            public_key       bytea NOT NULL,
            sign_count       bigint NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
            transports       text[] NOT NULL DEFAULT '{{}}',
            aaguid           text,
            backup_eligible  boolean NOT NULL DEFAULT false,
            name             text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
            created_at       timestamptz NOT NULL DEFAULT now(),
            last_used_at     timestamptz,
            revoked_at       timestamptz
        );
        CREATE TABLE auth.sessions (
            id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_sha256         text NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{{64}}$'),
            passkey_id           uuid NOT NULL REFERENCES auth.passkeys (id),
            client               text NOT NULL CHECK (client IN ('web', 'android', 'other')),
            device_name          text NOT NULL CHECK (length(device_name) BETWEEN 1 AND 100),
            ip_hash              text,
            created_at           timestamptz NOT NULL DEFAULT now(),
            last_used_at         timestamptz NOT NULL DEFAULT now(),
            expires_at           timestamptz NOT NULL,
            absolute_expires_at  timestamptz NOT NULL,
            revoked_at           timestamptz,
            CHECK (expires_at <= absolute_expires_at)
        );
        -- WebAuthn challenges for registration and login (5 minutes, single use).
        CREATE TABLE auth.challenges (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            purpose             text NOT NULL CHECK (purpose IN ('register', 'login')),
            challenge           bytea NOT NULL UNIQUE,
            session_id          uuid REFERENCES auth.sessions (id),
            enrolment_token_id  uuid,
            created_at          timestamptz NOT NULL DEFAULT now(),
            expires_at          timestamptz NOT NULL,
            used_at             timestamptz
        );
        -- Step-up: a fresh passkey assertion bound to one action and target,
        -- turned into a single-use token valid 120 s (contract §2).
        CREATE TABLE auth.step_ups (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id    uuid NOT NULL REFERENCES auth.sessions (id),
            action        text NOT NULL CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
            target        text NOT NULL CHECK (length(target) BETWEEN 1 AND 200),
            challenge     bytea NOT NULL UNIQUE,
            challenge_expires_at timestamptz NOT NULL,
            token_sha256  text UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{{64}}$'),
            verified_at   timestamptz,
            expires_at    timestamptz,
            used_at       timestamptz,
            created_at    timestamptz NOT NULL DEFAULT now()
        );
        -- `make owner-enroll`: one-time link, 15 minutes.
        CREATE TABLE auth.enrolment_tokens (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_sha256  text NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{{64}}$'),
            created_at    timestamptz NOT NULL DEFAULT now(),
            expires_at    timestamptz NOT NULL,
            used_at       timestamptz
        );
        ALTER TABLE auth.challenges ADD CONSTRAINT challenges_enrolment
            FOREIGN KEY (enrolment_token_id) REFERENCES auth.enrolment_tokens (id);

        GRANT SELECT, INSERT ON auth.passkeys, auth.sessions, auth.challenges, auth.step_ups,
            auth.enrolment_tokens TO hq_api;
        GRANT UPDATE (sign_count, last_used_at, revoked_at, name, backup_eligible)
            ON auth.passkeys TO hq_api;
        GRANT UPDATE (last_used_at, expires_at, revoked_at) ON auth.sessions TO hq_api;
        GRANT UPDATE (used_at) ON auth.challenges, auth.enrolment_tokens TO hq_api;
        GRANT UPDATE (token_sha256, verified_at, expires_at, used_at) ON auth.step_ups TO hq_api;
        -- The worker only purges expired challenges and step-ups.
        GRANT SELECT, DELETE ON auth.challenges, auth.step_ups TO hq_worker;

        -- ------------------------------------------------------------ owner --
        CREATE TABLE owner.presence (
            id          int PRIMARY KEY CHECK (id = 1),
            khalvat     boolean NOT NULL DEFAULT false,
            since       timestamptz NOT NULL DEFAULT now(),
            until       timestamptz,
            last_khalvat_start timestamptz,
            last_khalvat_end   timestamptz,
            version     int NOT NULL DEFAULT 1,
            updated_at  timestamptz NOT NULL DEFAULT now()
        );
        INSERT INTO owner.presence (id) VALUES (1);
        CREATE TRIGGER presence_version BEFORE UPDATE ON owner.presence
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();

        CREATE TABLE owner.settings (
            id                   int PRIMARY KEY CHECK (id = 1),
            timezone             text NOT NULL DEFAULT 'Asia/Tehran',
            morning_report_at    time NOT NULL DEFAULT '08:00',
            digest_minutes       int  NOT NULL DEFAULT 30 CHECK (digest_minutes BETWEEN 5 AND 720),
            ceo_daily_attention  int  NOT NULL DEFAULT 6 CHECK (ceo_daily_attention BETWEEN 0 AND 100),
            learning_daily_cap   int  NOT NULL DEFAULT 3 CHECK (learning_daily_cap BETWEEN 0 AND 20),
            calendars            text[] NOT NULL DEFAULT ARRAY['jalali', 'gregorian']
                                      CHECK (calendars <@ ARRAY['jalali', 'gregorian']
                                             AND cardinality(calendars) >= 1),
            -- WebAuthn user handle of the owner (opaque, random, not a secret).
            webauthn_user_id     bytea NOT NULL DEFAULT decode(replace(gen_random_uuid()::text, '-', ''), 'hex'),
            version              int NOT NULL DEFAULT 1,
            updated_at           timestamptz NOT NULL DEFAULT now()
        );
        INSERT INTO owner.settings (id) VALUES (1);
        CREATE TRIGGER owner_settings_version BEFORE UPDATE ON owner.settings
            FOR EACH ROW EXECUTE FUNCTION core.bump_version();
        CREATE TRIGGER owner_settings_immutable BEFORE UPDATE ON owner.settings
            FOR EACH ROW EXECUTE FUNCTION core.keep_immutable('webauthn_user_id');

        CREATE TABLE owner.interactions (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   uuid NOT NULL REFERENCES core.companies (id),
            at           timestamptz NOT NULL DEFAULT now(),
            kind         text NOT NULL CHECK (kind IN ('decision', 'rating', 'edit', 'message',
                                                       'setting', 'presence', 'answer', 'order',
                                                       'control', 'security')),
            action       text NOT NULL CHECK (action ~ '^[a-z_]+\.[a-z_]+$'),
            target_kind  text,
            target_ref   text,
            data         jsonb NOT NULL DEFAULT '{{}}' CHECK (jsonb_typeof(data) = 'object'),
            request_id   text
        );
        CREATE INDEX interactions_at ON owner.interactions (at DESC);
        CREATE TRIGGER interactions_append_only BEFORE UPDATE OR DELETE ON owner.interactions
            FOR EACH ROW EXECUTE FUNCTION core.reject_change();
        CREATE TRIGGER interactions_no_truncate BEFORE TRUNCATE ON owner.interactions
            FOR EACH STATEMENT EXECUTE FUNCTION core.reject_change();

        GRANT SELECT ON owner.presence, owner.settings TO {APP_ROLES};
        GRANT UPDATE (khalvat, since, until, last_khalvat_start, last_khalvat_end)
            ON owner.presence TO {APP_ROLES};
        GRANT UPDATE (timezone, morning_report_at, digest_minutes, ceo_daily_attention,
                      learning_daily_cap, calendars)
            ON owner.settings TO hq_api;
        GRANT SELECT, INSERT ON owner.interactions TO {APP_ROLES};
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
                ("notify", "notifications"),
                ("notify", "digest_batches"),
                ("owner", "interactions"),
            )
        )
    )


def downgrade() -> None:
    execute_script("DROP SCHEMA owner CASCADE; DROP SCHEMA auth CASCADE; DROP SCHEMA notify CASCADE")
