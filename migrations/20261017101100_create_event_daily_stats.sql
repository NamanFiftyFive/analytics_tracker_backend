-- migrate:up

-- Daily totals per event name; dashboards read this instead of raw events.

CREATE TABLE event_daily_stats (
    project_id     uuid NOT NULL,
    day            date NOT NULL,
    event_name     text NOT NULL,
    event_count    bigint NOT NULL,
    unique_persons int NOT NULL,
    PRIMARY KEY (project_id, day, event_name)
);

-- migrate:down

DROP TABLE IF EXISTS event_daily_stats;
