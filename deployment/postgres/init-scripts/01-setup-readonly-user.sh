#!/bin/bash
set -e

# This script runs during the first container startup or can be run manually.
# It uses the env variables defined in your docker-compose/env file.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 1. Create the user if they don't exist
    DO \$$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'readonly_user') THEN
            CREATE USER readonly_user WITH PASSWORD '$READONLY_USER_PASSWORD';
        END IF;
    END
    \$$;

    -- 2. Permissions: Standard Read-Only Access
    GRANT USAGE ON SCHEMA public TO readonly_user;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

    -- 3. Safety Switches: The "Anti-Lock" & "Anti-Spike" settings

    -- Kill any query taking longer than 30 seconds (Prevents 'SELECT *' from killing the DB)
    ALTER ROLE readonly_user SET statement_timeout = '30s';

    -- Kill any session 'Idle in Transaction' for more than 10 seconds (The "Forgot to Commit" fix)
    ALTER ROLE readonly_user SET idle_in_transaction_session_timeout = '10s';

    -- Kill totally idle connections after 15 minutes to free up slots
    ALTER ROLE readonly_user SET idle_session_timeout = '15min';

    -- Limit memory used for complex sorts/joins to 16MB (Prevents RAM exhaustion)
    ALTER ROLE readonly_user SET work_mem = '16MB';

EOSQL

echo "Read-only user 'readonly_user' configured with safety timeouts."