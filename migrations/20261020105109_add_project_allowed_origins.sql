-- migrate:up

-- Websites allowed to send events for this project, e.g. {'https://cars.example.com'}.
-- Checked against the browser's Origin header on ingest. Empty = any origin allowed.
-- Mobile apps send no Origin header and are not affected.
ALTER TABLE projects ADD COLUMN allowed_origins text[] NOT NULL DEFAULT '{}';

-- migrate:down

ALTER TABLE projects DROP COLUMN IF EXISTS allowed_origins;
