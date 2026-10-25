# Hosted snapshot backup and restore

This runbook backs up the V1 snapshot-authority database and its exact referenced
Supabase Storage objects. It runs on persistent local disk outside Render and never
uses hosted `/data/export`.

## 0. Local preflight and mandatory stop

Requirements: Python 3.10+, PostgreSQL 17 `psql`/`pg_dump`/`pg_restore`, this approved
repository revision, and at least 2 GiB free on private persistent storage. Docker is
optional for the recovery rehearsal. Python computes SHA-256, avoiding the macOS
`shasum` versus Linux `sha256sum` difference. On macOS, `brew install postgresql@17`
provides the clients; add its `bin` directory to `PATH`. Confirm all three PostgreSQL
tools report major version 17.

```sh
umask 077
export KE_BACKUP_ROOT="/private/persistent/path/ke-backup-$(date -u +%Y%m%dT%H%M%SZ)"
python scripts/backup_operator.py preflight "$KE_BACKUP_ROOT" --required-free-gib 2
```

This creates a mode-0700 empty directory, checks disk and prints `STOP: obtain approval
before suspending Render or using production credentials.` **Stop here.** Do not suspend
Render, load credentials, query production or download artifacts without approval.

## 1. Private credentials after approval

```sh
set +o history
umask 077
export PGSERVICEFILE="/private/credentials/pg_service.conf"
export PGPASSFILE="/private/credentials/.pgpass"
export KE_PG_SERVICE="ke_production_backup"
export KE_SUPABASE_URL="https://PROJECT.supabase.co"
export KE_STORAGE_BUCKET="knowledge-engine-artifacts"
export KE_WORKSPACE_KEY="configured-workspace-key"
export KE_SECRET_FILE="/private/credentials/supabase-secret"
chmod 600 "$PGSERVICEFILE" "$PGPASSFILE" "$KE_SECRET_FILE"
```

Keep database endpoint/password in the PostgreSQL service/pass files. The secret file
contains only the server-side Storage secret. Values must never enter Git, reports,
manifests, command arguments or captured output. Storage commands below expose the
secret only in their child-process environment.

## 2. Quiesce and capture the database fence

Suspend Render and confirm user writes and provider activity have stopped. Record the
deployed commit locally:

```sh
export KE_DEPLOYED_COMMIT="DEPLOYED_COMMIT_SHA"
```

The SQL files are executed by `psql --file`. Their `:'workspace'` expression is psql's
literal-safe interpolation: it quotes the value as a SQL literal, including embedded
quotes, without shell-built SQL.

```sh
psql "service=$KE_PG_SERVICE" -X -qAt -v ON_ERROR_STOP=1 \
  --set=workspace="$KE_WORKSPACE_KEY" --file=scripts/backup_sql/snapshot.sql \
  > "$KE_BACKUP_ROOT/snapshot.json.partial"
python - "$KE_BACKUP_ROOT/snapshot.json.partial" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); value=json.loads(p.read_text())
assert isinstance(value, dict) and value.get("partition") is None
PY
mv "$KE_BACKUP_ROOT/snapshot.json.partial" "$KE_BACKUP_ROOT/snapshot.json"

psql "service=$KE_PG_SERVICE" -X -qAt -v ON_ERROR_STOP=1 \
  --set=workspace="$KE_WORKSPACE_KEY" --file=scripts/backup_sql/consistency.sql \
  > "$KE_BACKUP_ROOT/consistency-before.json.partial"
python - "$KE_BACKUP_ROOT/consistency-before.json.partial" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); value=json.loads(p.read_text())
assert isinstance(value.get("revision"), int)
assert value.get("partition_marker") is None
assert isinstance(value.get("source_count"), int)
PY
mv "$KE_BACKUP_ROOT/consistency-before.json.partial" "$KE_BACKUP_ROOT/consistency-before.json"

pg_dump --dbname="service=$KE_PG_SERVICE" --format=custom --no-owner --no-acl \
  --schema=knowledge_engine --file="$KE_BACKUP_ROOT/database.dump.partial"
mv "$KE_BACKUP_ROOT/database.dump.partial" "$KE_BACKUP_ROOT/database.dump"
```

The dump includes snapshot, allowance state, allowance reservations and schema. Counts
are derived now; 63 sources and 189 references are comparison evidence, not permanent
assertions.

## 3. Metadata-only before inventory

```sh
SUPABASE_SECRET_KEY="$(cat "$KE_SECRET_FILE")" python scripts/backup_operator.py inventory \
  --url "$KE_SUPABASE_URL" --bucket "$KE_STORAGE_BUCKET" \
  --workspace "$KE_WORKSPACE_KEY" --snapshot "$KE_BACKUP_ROOT/snapshot.json" \
  --output "$KE_BACKUP_ROOT/metadata-before.ndjson"
```

This issues Storage list requests only. For each deduplicated snapshot locator it
requires one exact `$workspace/$locator` byte object, a unique nonempty object ID and a
nonnegative size. Output is locator-sorted deterministic NDJSON. Missing metadata,
duplicate matches or invalid identity stop before body GETs. Record the derived source,
artifact and byte counts; stop for review if a difference from prior evidence is not
explained by the fenced snapshot.

## 4. Sequential transfer

This is the first artifact-body read and the bandwidth authorization point:

```sh
SUPABASE_SECRET_KEY="$(cat "$KE_SECRET_FILE")" python scripts/backup_operator.py download \
  --url "$KE_SUPABASE_URL" --bucket "$KE_STORAGE_BUCKET" \
  --workspace "$KE_WORKSPACE_KEY" \
  --inventory "$KE_BACKUP_ROOT/metadata-before.ndjson" --package "$KE_BACKUP_ROOT"
```

Each object streams to `objects/<locator>.partial`; the tool hashes while reading,
checks metadata size and atomically renames only a complete object. It removes the
current partial on failure and writes `artifacts.ndjson` only after every transfer.
Objects outside the snapshot inventory are neither downloaded nor deleted.

## 5. After inventory, fence and manifest

```sh
SUPABASE_SECRET_KEY="$(cat "$KE_SECRET_FILE")" python scripts/backup_operator.py inventory \
  --url "$KE_SUPABASE_URL" --bucket "$KE_STORAGE_BUCKET" \
  --workspace "$KE_WORKSPACE_KEY" --snapshot "$KE_BACKUP_ROOT/snapshot.json" \
  --output "$KE_BACKUP_ROOT/metadata-after.ndjson"

psql "service=$KE_PG_SERVICE" -X -qAt -v ON_ERROR_STOP=1 \
  --set=workspace="$KE_WORKSPACE_KEY" --file=scripts/backup_sql/consistency.sql \
  > "$KE_BACKUP_ROOT/consistency-after.json.partial"
python - "$KE_BACKUP_ROOT/consistency-after.json.partial" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); value=json.loads(p.read_text())
assert isinstance(value.get("revision"), int)
PY
mv "$KE_BACKUP_ROOT/consistency-after.json.partial" "$KE_BACKUP_ROOT/consistency-after.json"

python scripts/backup_operator.py finalize --package "$KE_BACKUP_ROOT" \
  --deployed-commit "$KE_DEPLOYED_COMMIT"
python scripts/verify_hosted_backup.py "$KE_BACKUP_ROOT"
chmod -R go-rwx "$KE_BACKUP_ROOT"
```

Finalization requires equal parsed database fences and byte-identical Storage
inventories. It derives source, artifact, asset, job and output counts; rechecks every
checksum; and only then publishes `manifest.json`. Any revision, allowance,
reservation, object ID, size, timestamp or checksum change fails closed. Keep Render
quiesced until real recovery rehearsal succeeds or the attempt is abandoned.

## Isolated recovery rehearsal

```sh
export KE_RESTORE_ROOT="/private/persistent/path/ke-recovery-$(date -u +%Y%m%dT%H%M%SZ)"
python scripts/verify_hosted_backup.py "$KE_BACKUP_ROOT" --restore-local "$KE_RESTORE_ROOT"
```

Restore into a new PostgreSQL 17 database:

```sh
createdb ke_v1_recovery
pg_restore --exit-on-error --no-owner --no-acl \
  --dbname=ke_v1_recovery "$KE_BACKUP_ROOT/database.dump"
psql ke_v1_recovery -X -qAt -v ON_ERROR_STOP=1 \
  --set=workspace="$KE_WORKSPACE_KEY" --file=scripts/backup_sql/consistency.sql \
  > "$KE_BACKUP_ROOT/recovery-consistency.json"
```

Docker may supply PostgreSQL instead:

```sh
docker run --rm -d --name ke-v1-recovery-postgres \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_USER=ke_recovery \
  -e POSTGRES_DB=ke_recovery -p 127.0.0.1::5432 postgres:17-bookworm
docker port ke-v1-recovery-postgres 5432/tcp
pg_restore --exit-on-error --no-owner --no-acl \
  --dbname="host=127.0.0.1 port=LOCAL_PORT user=ke_recovery dbname=ke_recovery" \
  "$KE_BACKUP_ROOT/database.dump"
```

Compare recovery consistency JSON semantically with `consistency-before.json`. Inspect
the isolated snapshot for exact source IDs, Knowledge Asset IDs/count, extraction-job
counts grouped by preparation status, output/provenance history, allowance values and
reservation count. The verifier checks every artifact checksum and exact reference.
Start the app only with `KNOWLEDGE_ENGINE_STORAGE="$KE_RESTORE_ROOT/storage"`, local
persistence and no Gemini or hosted credentials. Never point rehearsal at live systems.

Keep the completed package on access-controlled encrypted persistent storage under the
owner-approved retention policy.
