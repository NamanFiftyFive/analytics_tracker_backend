-- migrate:up

-- Finds an event by id within a project, whatever its occurred_at. Ingest uses it to skip
-- events already stored: the primary key (project_id, occurred_at, id) can't catch a retry
-- whose occurred_at changed (device clock ahead, time replaced with the arrival time).
CREATE INDEX ix_events_project_id ON events (project_id, id);

-- migrate:down

DROP INDEX IF EXISTS ix_events_project_id;
