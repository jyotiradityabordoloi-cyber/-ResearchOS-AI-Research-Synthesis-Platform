-- Runs once when the Postgres volume is first created.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE researchos_test OWNER researchos;
\connect researchos_test
CREATE EXTENSION IF NOT EXISTS vector;
