-- migrate:up

-- One row each time an alert rule fires.

CREATE TABLE alert_history (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id        uuid NOT NULL REFERENCES alert_rules (id) ON DELETE CASCADE,
    triggered_at   timestamptz NOT NULL DEFAULT now(),
    observed_value numeric,
    status         text NOT NULL,
    details        jsonb,
    CONSTRAINT ck_alert_history_status CHECK (status IN ('sent', 'failed'))
);
CREATE INDEX ix_alert_history_rule_triggered ON alert_history (rule_id, triggered_at DESC);

-- migrate:down

DROP TABLE IF EXISTS alert_history;
