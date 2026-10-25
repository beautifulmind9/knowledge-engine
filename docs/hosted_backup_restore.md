# Hosted snapshot backup and restore

This runbook covers the V1 hosted layout: one authoritative JSONB row in
`knowledge_engine.state_snapshots`, the atomic allowance ledger in the same schema,
and private artifacts in Supabase Storage. The current production workspace has no
partition authority marker or partition tables. Do not invent one during backup or
restore.

The application `/data/export` is intentionally limited to 32 MiB of referenced
artifacts in hosted mode. The current 465.76 MiB active set must be backed up from an
operator machine to disk. The hosted worker must not build that archive.

## Acquire a current backup

Prerequisites are PostgreSQL 17 client tools, `curl`, `jq`, Python 3, at least 1 GiB
of free local disk, and the existing server-side database and Storage credentials.
Never put credentials in the manifest or shell history. Work in a new directory with
mode `0700`.

1. Stop or suspend the Render service so snapshot, ledger and artifact references
   cannot change. Record the deployed commit, workspace key, UTC time and reason.
2. Read the snapshot revision and confirm `payload->'partition' IS NULL`. Record its
   SHA-256 after writing the returned payload as `snapshot.json`.
3. Run `pg_dump --format=custom --no-owner --no-acl --schema=knowledge_engine
   --file=database.dump "$KNOWLEDGE_ENGINE_DATABASE_URL"`. This includes
   `state_snapshots`, `allowance_state`, all allowance reservations and the schema
   definitions. Hash the dump.
4. From `snapshot.json`, collect the exact nonempty `file_path`,
   `extracted_text_path` and `chunks_path` values. Deduplicate them. For this verified
   production snapshot the result must be 189 locators across 63 sources.
5. List Storage metadata under the exact workspace prefix. Join it to those locators.
   Require one byte object and a nonnegative size for every locator. Record the exact
   object key and metadata size. Do not include or delete the three unreferenced
   objects.
6. Download each referenced object separately with an authenticated Storage object
   GET directly to `objects/<locator>.partial`. Stream to disk, rename only after a
   successful response, then record its byte count and SHA-256. Never hold an object
   or aggregate archive in memory. Stop on any redirect, size mismatch or error.
7. Write `manifest.json` with `format_version: 1`, `authority: "snapshot"`, the
   deployed commit, workspace identifier, snapshot revision, acquisition timestamps,
   snapshot and database-dump file/checksum records, `allowance_ledger:
   {included_in_database_dump: true}`, and one artifact record containing `locator`,
   exact `object_key`, relative `file`, `size` and `sha256`.
8. Run `python scripts/verify_hosted_backup.py BACKUP_DIRECTORY`. Keep the service
   quiesced until verification and the isolated restore rehearsal pass.

Storage downloads consume egress. The procedure uses no paid service, but the owner
must authorize the approximately 465.76 MiB transfer and confirm it fits the current
allowance before acquisition.

## Isolated restore rehearsal

Never restore over live data.

1. Create a new empty local directory and run:

   `python scripts/verify_hosted_backup.py BACKUP_DIRECTORY --restore-local NEW_DIRECTORY`

   This verifies every checksum and exact snapshot reference, copies artifacts to an
   isolated storage tree, and creates an isolated SQLite snapshot database. Start a
   local app with `KNOWLEDGE_ENGINE_STORAGE=NEW_DIRECTORY/storage` and no hosted or
   provider credentials. Verify 63 materials, histories, provenance and representative
   artifact reads.
2. Restore `database.dump` into a newly created empty PostgreSQL 17 database with
   `pg_restore --exit-on-error --no-owner --no-acl --dbname=NEW_DATABASE database.dump`.
   Confirm exactly one expected workspace snapshot, its recorded revision and JSON
   hash, the allowance-state row, allowance reservations, and absence of a partition
   marker. Do not point an application at this database during verification.
3. For a hosted disaster recovery, create a new empty Storage workspace prefix and
   upload objects one at a time under each manifest `object_key`. Verify remote size
   and checksum where available before configuring an isolated recovery service.
4. Start the recovery service with provider calls disabled. Check health, material
   count, source scope, Knowledge Asset provenance, saved output history and allowance
   state. Switch traffic only after owner review.

## Rollback compatibility

The six-commit release candidate and `95c8f65` both load the current unpartitioned
snapshot format and use the same allowance tables. Rolling back exactly to `95c8f65`
requires no database downgrade or allowance copy-back. Quiesce requests, record the
ledger, deploy that immutable commit, and verify snapshot revision, source counts and
ledger values. The copy-back procedure is only for rollback to code predating ledger
authority.
