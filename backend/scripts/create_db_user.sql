-- Least-privilege application role for production.
-- Works on any Postgres (local, Supabase, RDS): it grants on whatever
-- database you run it in — no hardcoded database name.
--
-- Local:    psql -U postgres -d dbr_chatbot -f scripts/create_db_user.sql
-- Supabase: paste into the SQL Editor and Run.
--
-- Replace CHANGE_ME with a STRONG generated password first, e.g.:
--   python -c "import secrets; print(secrets.token_urlsafe(24))"
-- Then use dbr_app in DATABASE_URL. On Supabase's pooler the username
-- becomes dbr_app.<project-ref> (same suffix as your postgres user).
--
-- Keep running Alembic migrations as the owner user, not dbr_app.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dbr_app') THEN
        CREATE ROLE dbr_app LOGIN PASSWORD 'CHANGE_ME';
    ELSE
        ALTER ROLE dbr_app WITH LOGIN PASSWORD 'CHANGE_ME';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO dbr_app', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO dbr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dbr_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dbr_app;

-- future tables created by migrations (run as the owner) stay accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dbr_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO dbr_app;

-- explicitly no: CREATE, DROP, TRUNCATE, superuser, replication
