# Minimal generated-content integrity safeguard

Implementation baseline: `3f74cb00d5da5c74cf9e75900d040900a0e45753`,
branch `feature/knowledge-assets`. Offline implementation authorized by the owner;
this does not approve the full-source semantic reviewer judgments. Chunk001's
owner-approved material-omission decision and the reviewer-proposed remaining
failures remain separate in the preserved private evaluation.

## Boundary and policy

`complete_extraction_job(..., generated_content=True)` checks the whole candidate
chunk before asset IDs, accepted-asset mutation or coordinator settlement. Both
generated entrypoints opt in: independent extraction (including coalesced source
interpretation) and the retained batch service. Manual results keep the default
False; no manual import, snapshot loading or historical export is revalidated.
Future generated entrypoints must explicitly opt in at this boundary.

This supersedes the earlier design's proposed manual-import/evidence checks.
Strict internal models, provider schemas, prompts, model selection, extraction
versions and the gateway are unchanged.

The explicit prose-field allowlist covers title, what_it_says, why_it_matters,
application guidance lists and subtype explanations/actions/steps/components.
Each string list item is independent. Source evidence, chapter/section labels,
keywords, raw chunks, IDs and timestamps are excluded. No text is rewritten.

Detector `adjacent-word-periodicity-v1` measures casefolded word tokens over
periods 1–32. All four conditions must hold: field >=160 words, adjacent periodic
span >=128 words, >=8 complete cycles, periodic fraction >=0.60. A field over
16,384 characters emits a length diagnostic only. This is the characterized
conservative candidate policy, not a general coherence or factuality measure.

## Rejection lifecycle and visibility

A positive signal raises GeneratedContentIntegrityError, a subtype of the
existing ExtractionValidationError. The existing generated lifecycle marks the
job failed and source interpretation stops in the validation_failed category.
The retained batch service marks only the affected chunk failed, preserving its
existing independent chunk settlement semantics. No new review UI or status is
introduced.

The entire affected candidate chunk is rejected; no good sibling is published
and the previous generation remains unchanged. Provider success is already
counted. No repair, truncation, fallback or provider retry follows integrity
rejection. The existing confirmed-503-only retry remains confined to the gateway.

Job errors persist safe JSON diagnostics: detector/version, source/chunk/job IDs,
asset-index/field path, character/word counts, period, cycles, adjacent span,
fraction, length flag and reason. Structured events expose rejection or length
warning separately. Routine logs/errors retain neither the rejected prose nor
source excerpts; full rejected-provider-payload preservation is not introduced.
Structured logging remains best-effort; safe diagnostics also live in job.error.

## Offline evidence and limitations

The original 23 synthetic characterization tests remain. Structural parsing still
accepts the synthetic strings; the new generated settlement gate is separate.
The old corrupt manual-settlement test now explicitly documents unchanged manual
import behavior rather than claiming generated corruption remains accepted.

24 additional tests cover the fixture policy, 15-word/144-cycle repetition,
single-word degeneration, threshold conjunction/boundaries, period32, quoted
loops and ordinary quotation, source-text exclusions, list prose, generated
single/coalesced/batch rejection, no ID allocation/partial publication, previous
assets, safe persisted diagnostics, attempt counting/no retry, dispatcher stop,
empty results, coordinator pre-transaction boundary and legacy corrupted snapshot
readability. Existing allowance and confirmed-503 tests remain unchanged.

Limitations: fluent falsehoods, omissions, nonperiodic incoherence, symbol-only
blobs, periods over32 and repetition split across short list items may pass.
An intentional extreme repeated quote in generated prose may require review;
there is no quotation-mark exemption. Normal long prose and repeated headings
pass the fixtures. No guarantee of semantic quality follows a negative signal.
Future field/schema additions require reviewing the explicit prose allowlist.
No retrospective cleanup or migration is needed or performed.

All74 protected private evaluation files (including original assets, backups and
reviews) match their recorded SHA256 values. Frozen acceptance files match the
original committed protocol. Private runtime evidence remains Git-ignored.
No Gemini or hosted operation was performed. No new semantic acceptance decision
or permission for a live experiment is implied.

## Verification results

- Focused integrity/validation/interpretation/batch/allowance/retry: 114 passed.
- Full offline backend: 1,142 passed, two dependency deprecation warnings.
- Frontend: 182 passed; no frontend changes required.
- git diff --check: clean; no staged changes, commit or push.

An initial sandboxed backend run could not bind localhost for the existing demo
restart test; the final complete run with localhost permission passed. A new
coordinator-boundary test initially used an incomplete lookup stub; its setup was
corrected without changing the tested pre-transaction assertion. No outstanding
test failure remains.

Ready for owner acceptance of this limited safeguard. It does not resolve the
frozen evaluation's semantic omissions or authorize another provider request.
