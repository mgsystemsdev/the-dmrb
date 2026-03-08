# Postgres Migration Guide

This guide describes the Phase 3 preparation path for migrating an existing SQLite DMRB dataset to Postgres.

## 1) Start Postgres

Start a local Postgres instance and create an empty target database.

Example:

```bash
createdb dmrb
```

## 2) Set runtime configuration

For migration command:

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/dmrb
```

After migration, for app runtime:

```bash
export DB_ENGINE=postgres
export DATABASE_URL=postgresql://user:password@localhost:5432/dmrb
```

SQLite remains the default when `DB_ENGINE` is not set.

## 3) Run one-command migration

```bash
python -m scripts.migrate_to_postgres \
  --sqlite-path data/cockpit.db \
  --postgres-url "$DATABASE_URL"
```

The command performs:

- Postgres schema creation (`db/postgres_schema.sql`)
- SQLite export to JSON files
- JSON import into Postgres
- automatic integrity verification

## 4) Verify migration success

Migration succeeds only when verification passes:

- table record counts match
- primary entities exist in both stores
- required-field null parity matches

If verification fails, the command exits non-zero and prints detailed mismatches.

## 5) Switch and rollback strategy

Switch to Postgres:

- set `DB_ENGINE=postgres`
- set `DATABASE_URL`
- run the app normally

Rollback to SQLite:

- unset `DB_ENGINE` (or set `DB_ENGINE=sqlite`)
- ensure `COCKPIT_DB_PATH` points to the SQLite database
- run the app normally
