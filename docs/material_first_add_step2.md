# Slice 2B Step 2: material-first Add

Implemented for review, not committed. Doctrine: Capture naturally. Structure invisibly. Confirm visually.

## Interaction

Library's Add disclosure starts with the file picker. Home's existing Add to my library action opens it. Empty accounts no longer need to create a library first. The separate Create a library disclosure remains available, collapsed and below Add; source rows are unchanged.

File selection validates the supported extension, non-zero size and maximum 50,000,000 bytes (50 MB) per file locally. It writes nothing and invokes no provider. Backend upload validation remains authoritative. Only PDF, EPUB, DOCX, TXT, Markdown, HTML/HTM, CSV and JSON are offered.

After selection, “Here's what we found” shows filename, extension/format and byte-derived size, followed by an editable title explicitly labeled as suggested from filename and a visible destination. Change destination and optional author are progressive disclosures. The filename title remains provisional: deterministic reading may replace it with supported embedded metadata or clear title-page evidence. Only structured creator metadata or an explicit byline can fill an unknown author; ordinary names in prose are not treated as authors.

Title suggestion strips the final extension, replaces underscores/hyphens with spaces, collapses whitespace and uppercases the first character. Remaining capitalization and Unicode are preserved; the suggestion is capped at the backend's 500-character title limit.

Destination defaults to the current valid library, otherwise the first returned library. The default is always visible and editable. Empty accounts propose My Library; its name can be changed, and no library is created until Add. Existing accounts can choose another existing library or a named new destination.

## Writes and outcomes

An explicit Add runs, in order:

1. Create destination with POST /libraries, only if needed.
2. Create source with POST /sources.
3. Upload to POST /sources/{id}/upload.
4. Deterministically read/chunk with POST /sources/{id}/process.
5. Open source detail using the existing Step 1 summary.

No backend endpoint or persistence field is added. No temporary server-upload infrastructure or metadata-update endpoint is needed. Add never calls interpret/generate; successful reading shows Ready to build knowledge when supported by the summary. Build knowledge remains a separate explicit max_chunks=1 action. Existing partial sources use Continue building. The source read action is labeled Read source. Post-read copy distinguishes knowledge building from deterministic reading. Browse/Create actions and the idea preview depend on has_usable_knowledge, not coverage completion; partial usable knowledge remains available after a later build failure, while complete coverage with zero ideas does not advertise ideas. Advanced diagnostics remain accessible independently.

## Partial success and continuity

The in-tab Add state keeps the chosen File, confirmed metadata, acknowledged library/source identities, upload/read progress and safe endpoint failure message. It is not a durable workflow engine and is not atomic across endpoints.

- Destination creation failure: no source request; explicit retry.
- Source creation failure: acknowledged destination retained; no success claim; retry reuses that destination.
- Upload failure: source retained; Retry upload uses the same source. A replacement file can be chosen without another source creation.
- Read failure: source/file retained; Retry reading skips upload and source creation. A replacement supported file can be selected and explicitly uploaded/read against the same source, subject to existing backend replacement rules.
- OCR-required/scanned failures display the safe server explanation. After a failed read, the existing summary supplies the structured attention category. OCR-required recovery offers Choose a different file, then Use replacement file; it does not reread the unchanged artifact. Generic read failures retain Retry reading. No OCR is added or implied.

Open material is available after source identity exists. Returning to Library retains the in-tab incomplete flow. Source detail's missing-file upload retry validates locally and reads after upload. Cancelling before Add causes no writes. Back/Forward preserves the selected in-tab file/details until completion; successful Add opens a normal source route, and returning does not replay Add. Existing Create drafts are untouched.

Inputs and repeated Add activation are blocked during a running Add. Navigation cannot cause a late completion to redirect the user back; returning to the flow can show its current result. Refresh loses browser File/capture state, but acknowledged sources/files remain on the server and are accessible through existing source routes. A source/library creation response lost after an unknown server commit cannot be deduplicated by the current endpoints; no claim of exactly-once creation is made for that transport ambiguity.

## Verification and boundary

Frontend tests cover validation, title/defaults, ordered writes, failures, identity reuse, duplicate activation, cancellation and draft continuity. Synthetic browser acceptance covers empty/existing accounts, destination corrections, failed create/upload/read, OCR, history, mobile fit and no interpret/generate requests. Existing Create, Slice 2A, source-summary/recovery, auth/CSRF and artifact regressions remain required.

Screenshots are synthetic review artifacts under /tmp or ignored outputs, never commit inputs. Step 3 Library rows, final source hierarchy, Manage/Advanced restructuring, normal recovery polish and pagination remain deferred. No real Gemini calls are needed for this step.
