-- migrate:up

-- Shared enums and helper functions used by later tables.

CREATE TYPE member_role AS ENUM ('admin', 'analyst', 'viewer');
CREATE TYPE chart_type  AS ENUM ('line', 'bar', 'pie', 'number', 'table', 'funnel');

-- Keeps updated_at current on every UPDATE; attached per table with a trigger.
CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- migrate:down

DROP FUNCTION IF EXISTS set_updated_at();
DROP TYPE IF EXISTS chart_type;
DROP TYPE IF EXISTS member_role;
