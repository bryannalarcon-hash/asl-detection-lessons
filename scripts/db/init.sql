-- Postgres init script. Runs once when the named volume is first created.
-- Re-running `docker compose up` does NOT re-run this; use `docker compose down -v` to reset.
--
-- Real schema lives in the backend's migration files (Drizzle). The backend's
-- migration framework creates its own `__drizzle_migrations` table for tracking
-- applied migrations, so we don't need a hand-rolled bootstrap marker here.
-- This file only sets up Postgres-level extensions that have to exist before
-- any schema migration tries to use them.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- citext is intentionally NOT enabled here. If we decide we want case-insensitive
-- email columns, use a LOWER(email) unique functional index instead — more portable.
