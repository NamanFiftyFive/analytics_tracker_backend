-- migrate:up

-- Event triggers. on_event: fire when a matching event arrives.
-- threshold: fire when metric <operator> threshold within window_minutes.

CREATE TABLE alert_rules (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    name              text NOT NULL,
    trigger_type      text NOT NULL,
    event_name        text NOT NULL,
    metric            text NOT NULL DEFAULT 'count',
    operator          text,
    threshold         numeric,
    window_minutes    int,
    filters           jsonb NOT NULL DEFAULT '[]',
    channels          jsonb NOT NULL,
    cooldown_minutes  int NOT NULL DEFAULT 60,
    is_active         boolean NOT NULL DEFAULT true,
    last_evaluated_at timestamptz,
    last_triggered_at timestamptz,
    created_by        uuid REFERENCES users (id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_alert_rules_trigger_type CHECK (trigger_type IN ('on_event', 'threshold')),
    CONSTRAINT ck_alert_rules_metric       CHECK (metric IN ('count', 'unique_persons')),
    CONSTRAINT ck_alert_rules_operator     CHECK (operator IN ('>', '>=', '<', '<=')),
    CONSTRAINT ck_alert_rules_window       CHECK (window_minutes > 0),
    CONSTRAINT ck_alert_rules_cooldown     CHECK (cooldown_minutes >= 0),
    CONSTRAINT ck_alert_rules_threshold_fields CHECK (
        trigger_type = 'on_event'
        OR (operator IS NOT NULL AND threshold IS NOT NULL AND window_minutes IS NOT NULL)
    )
);
CREATE INDEX ix_alert_rules_project_event ON alert_rules (project_id, event_name);

-- migrate:down

DROP TABLE IF EXISTS alert_rules;
