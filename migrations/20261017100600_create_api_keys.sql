-- migrate:up

-- Keys SDKs use to send events. Only a hash is stored; the full key is shown once at creation.

CREATE TABLE api_keys (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    name         text NOT NULL,
    key_prefix   varchar(16) NOT NULL,
    key_hash     text NOT NULL,
    last_used_at timestamptz,
    revoked_at   timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash)
);
CREATE INDEX ix_api_keys_project_id ON api_keys (project_id);

-- migrate:down

DROP TABLE IF EXISTS api_keys;
