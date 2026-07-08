-- Least-privilege application role for production.
-- Run as the postgres superuser, ONCE, after migrations have been applied:
--   psql -U postgres -d dbr_chatbot -f scripts/create_db_user.sql
--
-- Replace CHANGE_ME with a strong generated password, then set it in .env:
--   DATABASE_URL=postgresql+asyncpg://dbr_app:<password>@localhost:5432/dbr_chatbot
--
-- The app role can read/write data but cannot DROP tables, create roles,
-- or alter the schema. Alembic migrations keep running as the table owner.

CREATE ROLE dbr_app LOGIN PASSWORD 'CHANGE_ME';

GRANT CONNECT ON DATABASE dbr_chatbot TO dbr_app;
GRANT USAGE ON SCHEMA public TO dbr_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO dbr_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dbr_app;

-- future tables created by migrations (run as the owner) stay accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dbr_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO dbr_app;

-- explicitly no: CREATE, DROP, TRUNCATE, superuser, replication
