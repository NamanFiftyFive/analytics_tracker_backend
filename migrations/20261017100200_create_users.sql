-- migrate:up

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text NOT NULL,
    password_hash  text NOT NULL,
    full_name      text,
    is_active      boolean NOT NULL DEFAULT true,
    last_login_at  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Email is unique regardless of letter case.
CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));

-- migrate:down

DROP TABLE IF EXISTS users;
