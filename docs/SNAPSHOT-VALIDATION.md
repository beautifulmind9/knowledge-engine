# Clean snapshot validation and publication boundary

Status: prepared for owner review only. No push or provider operation is authorized by this document.

## Exact scope and audit

42 staged files: 33 byte-identical allowlisted copies and nine generated documentation/configuration/test files.
`PUBLICATION-MANIFEST.json` enumerates every path, records SHA-256 for each copied file and identifies its origin.
No original Git metadata, refs, object store, working-tree index, storage or inherited ancestry was copied.
The local root commit is the candidate publication artifact, not a release or semantic-quality approval.

All staged bytes were checked against the explicit manifest, original copy hashes, secret patterns and excluded
legacy/private artifact hashes. No book PDF, book-derived JSON, private receipt, provider response, archive,
credential, personal workspace path, incident export or private runtime record is included. All files are text;
no symlink or submodule is included. No Git alternates or shallow history are configured.

One deliberately reviewed equality is not a private-evidence leak: the public, explicitly original synthetic
repair-session source is also duplicated inside private synthetic test workspaces. Its approved SHA-256 is
`93afffd120832c93694a2e854e4a8dd444e0d1f83bc05d812ab7d49390485de8`.
Only the already tracked synthetic source file was copied; none of those private runtime artifacts was copied.
989 text fields across the benchmark fixture/results were verified against the three reviewed synthetic
source texts. No source passages are inferred from missing evidence. Pattern scans supplement human review;
they do not prove semantic correctness, legal clearance of every phrase or universal secret absence.

## Independently rerun checks

- Python: **28 passed** (24 existing prototype regressions plus four snapshot-manifest/syntax/rights checks).
- Node source-search preview: **3 passed, 0 failed**.
- Synthetic parser probes: DOCX, HTML and PDF all completed; retained image-only PDF limitation confirmed.
- Python/API/tool reference files parsed without importing the incomplete application.
- Copied benchmark results and all source/fixture files remain byte-identical. Parser/evaluation entry points
  that rewrite result JSON were not used; no historical timings were replaced by new hardware measurements.
- Network was blocked in Python test/probe execution; the Node test supplies a fake API. No Gemini count,
  generation, repair, deployment or production database operation was performed.

Commands run in this isolated snapshot, using an existing local environment (no installation):

```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q
node --test apps/web/tests/source-search.test.mjs
```

The parser probe was called as a Python function with socket creation denied, without writing result JSON.
Environment: Python 3.12 environment, pytest 9.1.1, SQLite 3.53.0 with FTS5, python-docx 1.2.0, pypdf 6.18.1;
existing beautifulsoup4/EbookLib also satisfy the pure-parser imports. These are observed versions, not a claim
that a fresh install or every platform has been validated.

The staged whitespace check reports only the two existing Markdown hard-line-break spaces in the frozen
synthetic source header. Those exact bytes are intentionally preserved to retain the source fingerprint.

## Explicit non-results and preservation

The six copied application test modules cannot run independently: this snapshot intentionally omits the app
entry point, shared client fixtures, persistence/authority adapters and broader runtime dependencies.
No full backend/frontend rerun or new live-answer success is claimed. Historical full-suite results remain
historical. Count and generation scripts are reference-only, lack private prerequisites and must not be run
from this preservation snapshot. The old count receipt expired; no recount or generation is authorized.

Before preparing the root commit, original research HEAD/status, all 33 copied originals, 21 existing private
research artifacts and original development HEAD/status were verified unchanged. Original modified/untracked
work remains in its original checkout. No file was moved or deleted. Backups were read only for preservation
hash checks and never altered. The accepted integrity safeguard and rejected extraction experiment remain
independent; neither is changed or promoted here. Cashvertising Online production correction remains NO-GO.

The proposed remote branch name `research/source-first-public-snapshot` was absent from GitHub when checked
with `git ls-remote --heads`; repeat this check immediately before any separately approved publication.
No remote is configured in this temporary repository. The inherited published PDF issue is documented
separately in `PDF-HISTORY-ISSUE.md`; no remediation was attempted.
