-- migrate:up

-- An end user of a tracked app, identified by the SDK's distinct_id.

CREATE TABLE persons (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    distinct_id   text NOT NULL,
    properties    jsonb NOT NULL DEFAULT '{}',
    first_seen_at timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    CONSTRAINT uq_persons_project_distinct UNIQUE (project_id, distinct_id)
);

-- migrate:down

DROP TABLE IF EXISTS persons;
