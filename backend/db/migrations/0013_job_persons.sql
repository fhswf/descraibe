-- Migration: Add job_persons table for persistent person metadata storage
-- Stores detected persons with their attributes and appearance history

CREATE TABLE IF NOT EXISTS job_persons (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    person_id       INTEGER NOT NULL,
    name            TEXT,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_ts   DOUBLE PRECISION NOT NULL,
    last_seen_ts    DOUBLE PRECISION NOT NULL,
    description     TEXT,
    appearances     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, person_id)
);

CREATE INDEX IF NOT EXISTS idx_job_persons_job_id ON job_persons(job_id);
CREATE INDEX IF NOT EXISTS idx_job_persons_first_seen ON job_persons(first_seen_ts);

-- Record migration in schema_migrations
INSERT INTO schema_migrations (version) VALUES ('0013_job_persons')
ON CONFLICT (version) DO NOTHING;