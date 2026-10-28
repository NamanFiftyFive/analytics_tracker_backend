-- migrate:up

-- Which users belong to which organization, and their role there.

CREATE TABLE organization_members (
    organization_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role            member_role NOT NULL DEFAULT 'viewer',
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, user_id)
);
CREATE INDEX ix_organization_members_user_id ON organization_members (user_id);

-- migrate:down

DROP TABLE IF EXISTS organization_members;
