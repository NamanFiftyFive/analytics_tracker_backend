-- migrate:up

-- Raw events: append-only, partitioned by month. No foreign keys so bulk
-- ingestion stays fast; the API validates project_id before inserting.

CREATE TABLE events (
    id           uuid NOT NULL,                     -- client-generated, dedupes retries
    project_id   uuid NOT NULL,
    event_name   text NOT NULL,
    distinct_id  text NOT NULL,
    person_id    uuid,
    session_id   uuid,
    occurred_at  timestamptz NOT NULL,              -- client time, partition key
    received_at  timestamptz NOT NULL DEFAULT now(),
    source       text NOT NULL DEFAULT 'api',
    path         text,
    screen_name  text,
    platform     text,
    os           text,
    browser      text,
    device_type  text,
    app_version  text,
    country      char(2),
    properties   jsonb NOT NULL DEFAULT '{}',
    CONSTRAINT pk_events PRIMARY KEY (project_id, occurred_at, id),
    CONSTRAINT ck_events_source CHECK (source IN ('api', 'csv', 'excel'))
) PARTITION BY RANGE (occurred_at);

CREATE INDEX ix_events_project_name_time     ON events (project_id, event_name, occurred_at);
CREATE INDEX ix_events_project_distinct_time ON events (project_id, distinct_id, occurred_at);
CREATE INDEX ix_events_session_id            ON events (session_id);

-- Creates the monthly partition that contains p_month (UTC), e.g. events_2026_10.
-- Safe to call repeatedly; a scheduled job will call it for next month.
CREATE FUNCTION create_events_partition(p_month date) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    start_ts  timestamptz := date_trunc('month', p_month::timestamp) AT TIME ZONE 'UTC';
    end_ts    timestamptz := (date_trunc('month', p_month::timestamp) + interval '1 month') AT TIME ZONE 'UTC';
    part_name text        := format('events_%s', to_char(p_month, 'YYYY_MM'));
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF events FOR VALUES FROM (%L) TO (%L)',
        part_name, start_ts, end_ts
    );
    RETURN part_name;
END;
$$;

SELECT create_events_partition('2026-10-01');
SELECT create_events_partition('2026-11-01');
SELECT create_events_partition('2026-12-01');

-- Catches events outside every monthly partition (e.g. bad client clocks).
CREATE TABLE events_default PARTITION OF events DEFAULT;

-- migrate:down

DROP TABLE IF EXISTS events;          -- drops all partitions too
DROP FUNCTION IF EXISTS create_events_partition(date);
