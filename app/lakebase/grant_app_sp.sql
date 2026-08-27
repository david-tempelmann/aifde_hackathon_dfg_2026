-- Grant the app read access to the synced Gold tables.
--
-- The Lakebase `gold` tables are created/owned by the sync pipeline's role
-- (databricks_writer_*), not by the app or the deployer, so the app's service
-- principal starts with no read privilege on them. We can't grant
-- databricks_superuser (no ADMIN option) or grant on the writer-owned tables as
-- a non-owner — but the deployer OWNS the `gold` schema, which is enough to grant
-- read to PUBLIC (covers the app SP).
--
-- Run as the gold-schema owner against databricks_postgres after the synced
-- tables exist. Re-run if a future sync recreates a table (TRIGGERED incremental
-- refreshes reuse existing tables, so this normally persists).
GRANT USAGE ON SCHEMA gold TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO PUBLIC;
