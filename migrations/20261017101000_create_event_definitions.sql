-- migrate:up

-- Catalog of event names seen per project (powers event pickers in the UI).

CREATE TABLE event_definitions (
    project_id    uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    event_name    text NOT NULL,
    description   text,
    first_seen_at timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    PRIMARY KEY (project_id, event_name)
);

-- migrate:down

DROP TABLE IF EXISTS event_definitions;
