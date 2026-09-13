# Storage and privacy decision

Decision recorded 2026-09-13. Scope: small, single-owner local beta at a zero infrastructure cost.

## Choice and trade-offs

Use SQLite on a persistent local disk plus private source files. Keep the existing inspectable record collections and commit a complete state snapshot in one SQLite transaction. This avoids a hosted database, billing account, or complex migration before beta validation. Libraries, sources, jobs, assets, outputs, revisions and usage are included.

SQLite transactions protect against partial snapshot writes. A single-process lock and serialized requests avoid two normal servers writing stale snapshots. The trade-off is coarse concurrency, increasing snapshot cost as data grows, and no transactional atomicity between file operations and database writes. Disk failures can leave missing files, which the integrity endpoint detects. The beta is not suitable for multiple workers or teams.

Alternatives deferred: normalized SQLite tables (better scaling, more migration work), hosted Postgres (unneeded account/infrastructure work), JSON-only snapshots (weaker durability). Existing JSON state is imported on first startup only if no SQLite snapshot exists. The original JSON is preserved; corrupt JSON fails loudly.

## Backup and restore

1. Download the private ZIP from Data & usage. It includes source uploads, extracted text, chunks, record history and a portable JSON snapshot.
2. Stop the server before restoring. Extract into a new empty folder; never overwrite a live database.
3. Set `KNOWLEDGE_ENGINE_STORAGE` to the absolute path of the extracted storage folder, which may be renamed.
4. Restart with one worker and inspect Data & usage for integrity issues. Open an output and its history.

The regression suite restores into a renamed folder in a fresh process and verifies provenance and output history. Back up before migrating your own real-book data. A backup on an ephemeral filesystem is not a durable backup; choose your own persistent disk and backup location.

## Privacy boundaries

- The app is loopback-only with host/origin checks, not a multi-user security boundary. It has no authentication or at-rest encryption. OS account/disk protection is the owner's responsibility.
- The static mount is limited to web assets. Uploaded files are served only through source endpoints; never expose this app publicly.
- An explicit AI request sends the selected chunk or evidence and brief to Google. `store=false` disables interaction storage for later retrieval; provider-wide policies still apply.
- No API calls occur during demo seeding, manual import/editing, or automated tests.
- Source deletion can remove dependent output histories, which must be explicitly selected; retained outputs are not silently detached from their evidence.
- Backups and pre-migration `state.json` may retain deleted records. App deletion does not erase separately retained backups or the preserved migration file. Manage those separately.
- `.env`, private storage, SQLite files and generated outputs are ignored by git. Keep custom storage directories outside the repository or explicitly ignored. Public examples contain only original synthetic material.

## Known limits

Integrity checks detect missing files and several broken record links; they do not prove semantic evidence quality. Consolidation preserves raw assets and uses lexical similarity, with conservative tension flags. Large-source quality, complete chapter provenance, and human output review are release gates rather than assumed properties.
