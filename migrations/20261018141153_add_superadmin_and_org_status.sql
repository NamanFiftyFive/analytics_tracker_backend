-- migrate:up

-- Platform owner(s). Super admins can manage every organization and act as admin inside any of
-- them. Set only by scripts/create_superadmin.py, never through the API.
ALTER TABLE users ADD COLUMN is_superadmin boolean NOT NULL DEFAULT false;

-- Suspended organizations (is_active = false) can't be used by their members.
ALTER TABLE organizations ADD COLUMN is_active boolean NOT NULL DEFAULT true;

-- migrate:down

ALTER TABLE organizations DROP COLUMN IF EXISTS is_active;
ALTER TABLE users DROP COLUMN IF EXISTS is_superadmin;
