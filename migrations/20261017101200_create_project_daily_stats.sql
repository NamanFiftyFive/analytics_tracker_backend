-- migrate:up

-- Daily project-wide numbers (active users, sessions, ...), rebuilt from events.

CREATE TABLE project_daily_stats (
    project_id           uuid NOT NULL,
    day                  date NOT NULL,
    active_users         int NOT NULL,
    new_users            int NOT NULL,
    sessions             int NOT NULL,
    total_events         bigint NOT NULL,
    avg_session_seconds  int NOT NULL,
    bounce_rate          numeric(5, 2),
    PRIMARY KEY (project_id, day)
);

-- migrate:down

DROP TABLE IF EXISTS project_daily_stats;
