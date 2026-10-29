# Source-first research: isolated preservation snapshot

**Experimental research, not a runnable Knowledge Engine product or production release.**
Proposed remote branch: `research/source-first-public-snapshot`. Publication remains pending owner approval.
This repository starts with a new root commit; it copies only the explicit SHA-256 allowlist in
`PUBLICATION-MANIFEST.json`. It has no ancestry from the application repository.
The existing LICENSE is preserved; this snapshot does not grant a new open-source license.

## What runs independently

The standalone SQLite FTS5/BM25 prototype and 26-query synthetic benchmark use zero Knowledge Assets,
no app startup, no provider and no production database. Python with SQLite FTS5 and pytest is required.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest
```

The tests block socket creation. They retain known retrieval failures rather than changing labels.
The fixture and its SHA-256 are unchanged. Its repair-session source explicitly declares original,
fictional synthetic material, not text copied from a publication. Other corpus sources are synthetic too.
No original book, private audit, provider output, receipt, key, ZIP or application state is included.

The optional `multimodal_probe.py` can load the copied pure parser functions through AST without
application initialization, using python-docx, pypdf, beautifulsoup4 and EbookLib. Its script entry point
rewrites only the snapshot's result JSON; the preservation audit instead calls `run()` without writing it.
Likewise `evaluate.py` script mode rewrites results; tests use its in-memory evaluator. Do not overwrite
preserved measurements merely to substitute new hardware timings.

## Reference-only integration code

The selected `apps/api/` modules and tests preserve implemented contracts, not an independently runnable API.
The snapshot intentionally omits app startup, persistence authority, artifact adapters, configuration,
gateway dependencies, application fixtures and original full-suite harness. Integration tests here are
not collected by default and must not be described as independently passing. Copying a module is not
approval to deploy it. `apps/web/source-search.js` and its VM test are independently runnable with Node.

`tools/source_answer_count.py` and `tools/source_answer_generate.py` are **historical, reference-only**
one-shot tools coupled to a private synthetic workspace and implementation hashes. They are not a public
execution procedure. No corresponding private state or receipt is present. Do not run prepare/count/generate
from this snapshot or recreate missing evidence. The historical receipt expired on 2026-10-21; no current
counting or generation authorization is inferred. This snapshot performs no provider request of any kind.

## Interfaces and findings

See `docs/ARCHITECTURE-AND-HANDOFF.md` for the actual implemented boundaries, measured findings,
known failures, hybrid retrieval reuse and integration prerequisites. See `docs/PDF-HISTORY-ISSUE.md`
for a separate record of inherited published material excluded from this snapshot.
Historical source worktree: research checkpoint `c9641fb68c83eb1fa38354d42ba329b2cf28ff3b`, plus explicitly
allowlisted uncommitted research files. Source code is preserved byte-for-byte. This does not promote the
rejected extraction candidate, change the main application, or resolve Measuring Narrative Engagement.
Cashvertising Online production correction remains **NO-GO**.
