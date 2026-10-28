-- migrate:up

-- A graph on a dashboard. `query` describes what to plot, e.g.
-- {"event": "signup", "metric": "unique_persons", "interval": "day", "date_range": "last_30d"}

CREATE TABLE widgets (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id uuid NOT NULL REFERENCES dashboards (id) ON DELETE CASCADE,
    title        text NOT NULL,
    chart_type   chart_type NOT NULL,
    query        jsonb NOT NULL,
    layout       jsonb NOT NULL DEFAULT '{"x": 0, "y": 0, "w": 6, "h": 4}',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_widgets_dashboard_id ON widgets (dashboard_id);

CREATE TRIGGER trg_widgets_updated_at
    BEFORE UPDATE ON widgets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- migrate:down

DROP TABLE IF EXISTS widgets;
