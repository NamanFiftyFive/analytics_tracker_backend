-- migrate:up

-- One tracked app or website inside an organization.

CREATE TABLE projects (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    name            text NOT NULL,
    platform        text NOT NULL,
    timezone        text NOT NULL DEFAULT 'UTC',
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_projects_platform
        CHECK (platform IN ('web', 'ios', 'android', 'flutter', 'other'))
);
CREATE INDEX ix_projects_organization_id ON projects (organization_id);

-- migrate:down

DROP TABLE IF EXISTS projects;
