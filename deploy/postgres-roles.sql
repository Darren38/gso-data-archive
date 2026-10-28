-- Separate privileges: the collector writes, the public API only reads.
-- Run as the database owner after `gso-archive migrate`. Replace the passwords.

CREATE ROLE gso_reader LOGIN PASSWORD 'CHANGE_ME_READER';
GRANT CONNECT ON DATABASE gso_archive TO gso_reader;
GRANT USAGE ON SCHEMA public TO gso_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO gso_reader;
-- Tables created by future migrations (run by the writer role) are readable too:
ALTER DEFAULT PRIVILEGES FOR ROLE gso_writer IN SCHEMA public GRANT SELECT ON TABLES TO gso_reader;
-- Keep raw-response bookkeeping private if desired:
-- REVOKE SELECT ON raw_snapshots FROM gso_reader;
