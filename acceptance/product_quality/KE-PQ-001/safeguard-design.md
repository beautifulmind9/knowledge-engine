> Historical design baseline. The authorized implementation and its narrower
> generated-only scope are recorded in [integrity-implementation.md](integrity-implementation.md).
> Manual imports and source-evidence fields are excluded by the later owner policy.
> Original design discussion and offline findings below are retained for traceability.

# KE-PQ-001 — generated-content integrity safeguard design

Status: diagnostic/design baseline only. No application gate is implemented.
Original frozen evaluation is under `acceptance/extraction_quality_2026-10-17/`;
this separate record does not amend its source, rubric or protocol. Application
baseline is `3f74cb0`. Private source/asset/job/audit/review evidence remains under
Git-ignored acceptance storage; do not force-add it. Only original synthetic
fixtures, characterization tests and this design are candidates for Git tracking.

## Decision and evidence preservation

Technical execution: four successful counted provider attempts, 25 structurally
validated assets, available provenance intact and four verified backups.
Chunk001 FAIL — MATERIAL OMISSION is owner-approved. The full-source FAIL and new
chunk002–004 scores/critical-content findings are reviewer assessments awaiting
owner approval. The latest request does not silently supply that approval.
Original assets, raw API records, execution markers, backups, prior reviews and
frozen files are preserved by a separate private SHA-256 baseline manifest.
Raw provider JSON before adaptation is unavailable; no reconstruction is claimed.

## Confirmed mechanism

1. `validate_extraction_result()` calls
   `KnowledgeExtractionResultSubmission.model_validate_json()` on returned text.
   `BaseKnowledgeAsset.why_it_matters` is `str | None` without a maximum length,
   repetition bound, field-level support check or coherence constraint.
2. Structural validity therefore includes very long, repetitive or unsupported
   explanations. That is a validation boundary, not a weakened discriminator:
   chosen subtype fields and provenance rules remain strict.
3. The generated path assigns system-owned IDs/provenance, then calls
   `complete_extraction_job()`. It builds the complete typed asset batch before
   superseding old active assets and publishing the replacement. Manual imports
   and the retained batch service also reach this shared settlement function.
4. The existing source evidence audit searches normalized evidence text (and
   ordered ellipsis fragments) in the chunk. It does not establish the support or
   coherence of `why_it_matters` or every other populated field.
5. The retained bad rationale is 21,365 characters / 2,272 words. Its 15-word
   periodic run occupies 2,160 words (95.07%) and repeats 144 times. Unsupported
   legal/safety assurances are semantic findings; the extreme adjacent loop is
   a deterministic integrity signal. The short correct evidence quote cannot
   validate the entire payload.
6. The field is present in the earliest retained successful API response and
   subsequent assets/backups. This rules out a later UI-only artifact, but absent
   raw provider text prevents a definitive claim about provider-internal cause.

## Smallest proposed gate — not production behavior

Keep the strict KnowledgeAsset models, provider schema, prompts and allowance/
retry behavior unchanged. Add one deterministic content-integrity check to the
shared extraction settlement boundary **before any asset IDs are allocated,
old assets superseded, new assets appended or settlement transaction begun**.
Validate the entire proposed asset list before changing accepted knowledge.

Inspect human-content fields, including subtype text and each textual list item;
exclude identifiers, timestamps, transport metadata and the raw source chunk.
Use field-level measurements, not repetition across separate assets/chunks.

The test-only design probe measures normalized adjacent word periodicity over
periods 1–32. A conservative candidate signal requires all of:

- at least 160 field words;
- a periodic adjacent span of at least 128 words;
- at least 8 complete cycles;
- at least 60% of field words in that span.

These are proposed calibration values, not settled production limits. They catch
the actual retained 144-cycle field and synthetic phrase/single-word degeneration.
An O(32*n) measurement avoids quadratic repetition scans. Case/punctuation
normalization is for measurement only; never rewrite the actual asset text.
Scan each field/list item; aggregating repeated words across unrelated fields
would create false positives. A future global work cap must fail explicitly,
not silently skip checks; no such production limit is implemented here.

### Exceptional length

The probe records `>16,384 characters` as a diagnostic only. Length alone is NOT
an automatic rejection criterion: a coherent synthetic explanation longer than
the observed 21,365-character defect is accepted by the candidate experiment.
No clipping, silent summarization, token estimation or source-length ratio is
proposed as a semantic gate. A future configurable transport/resource cap is a
separate decision and must preserve valid long material or return an explicit
review/size outcome. Do not change model schema lengths as a shortcut here.

### Fail closed to ordinary acceptance, not a semantic verdict

When the strong repetition signal fires, reject settlement of the **whole chunk
result**, including otherwise good siblings. Do not save only good assets, turn
the result into a valid empty list, or supersede an older accepted set. The
signal means “content integrity requires review,” not “the source contains no
knowledge” or “every claim is false.”

Reuse the existing failed generated-job lifecycle and validation-failed source
interruption presentation. No new database lifecycle state is required. Translate
the shared integrity exception into the existing generated validation failure
category; do not misclassify it as a provider/network outage. Keep exception
ownership free of circular imports. The manual-results API must reject the request
without publishing any assets; preserving its existing pending-job behavior for
invalid manual submissions avoids unrelated lifecycle redesign.

A shared gate covers manual imports too. The retained multi-chunk service needs
safe per-chunk exception mapping if used; do not silently add shared-context
provider calls or alter atomicity across independently settled chunks. Only the
corrupt chunk's candidate batch is rejected; unrelated completed chunks remain.

The provider attempt was already admitted and counted. Keep it counted. Do not
repair, trim, re-prompt, change model or invoke the provider again. The gateway's
confirmed-503 retry applies only to provider responses before validation; an
integrity failure after successful generation must not trigger it. Ordinary
explicit recovery remains subject to existing authorization and quota rules.

### Review and audit visibility

Suggested user message: “AI returned highly repetitive text. No new knowledge was
saved. Previous knowledge is unchanged. This attempt was counted.” Explain that
review is needed; do not label the source empty, silently continue siblings, or
promise semantic correctness for responses that do not trigger the signal.

Record a versioned reason code, job/chunk/asset-index/field path, character/word
counts, period, cycle count, span fraction and content hash. Avoid raw content,
credentials and headers in normal logs or job errors. Existing `job.error` plus
structured events can expose the failure without a migration. Provider success,
structural success, integrity rejection and settlement outcome must stay distinct.
Full rejected-payload retention in a separate private diagnostic artifact is an
owner decision, not a prerequisite silently implemented by this design; retaining
only metrics/hash limits later semantic inspection and must be disclosed.

## Deterministic limitations and false positives

- Fluent unsupported claims and non-repetitive nonsense can pass this signal.
  It is not a general coherence, entailment or completeness validator.
- An intentional long repeated quotation can trigger the same measurement. Stop
  ordinary acceptance for review; do not automatically call that text fabricated.
  Do not add a hidden whitelist or automatic source-match bypass.
- A huge punctuation-only blob triggers the exceptional-length diagnostic but not
  this word-periodicity signal. That is a documented gap, not passing content.
- Legitimate repeated headings, shared terminology and same-source cross-chunk
  overlap are not evidence of field corruption. Tests cover these distinctions.
- Threshold calibration beyond these fixtures remains limited. No guarantee is
  inferred from one frozen source or from fixture pass rates.

## Offline baseline versus future acceptance requirements

Current characterization tests explicitly show that the app accepts the synthetic
loops and publishes a structurally valid corrupted replacement. Passing those
baseline tests means the defect is reproduced, NOT prevented. A strict-schema
failure still rejects the whole submitted batch and preserves prior active assets.
The standalone test helper measures a proposed signal; the application never
imports it. Unimplemented acceptance requirements remain this checklist, not fake
passing enforcement tests:

1. Severe repeated phrase/single-word fields reject the entire generated result
   before settlement; no good sibling is published and prior active assets/history
   remain intact. Test first extraction and explicit replacement.
2. Inspect title, summary, explanation, evidence and subtype/list content with
   safe field paths. No mutation to accepted text or provider-facing schema.
3. Valid long explanations, recurring terms and separated repeated headings pass.
   Intentional extreme source quotations are explicitly reviewable false positives.
4. Test local snapshots and dormant hosted coordinator boundaries with fakes only;
   no hosted operation or migration. Gate must precede all asset writes.
5. Generated failure marks the job failed with a safe validation category; manual
   invalid submission stays unpublished. Source dispatcher stops before another
   provider call. Successful empty output remains valid and is not retried.
6. Exactly one attempt remains counted for an integrity failure after success.
   No repair/fallback/503 retry is caused by content. Existing 503 tests still pass.
7. Structural subtype validation, provenance matching, snapshot/history semantics
   and unrelated extraction/retrieval/Create behavior remain unchanged.
8. Safe diagnostics survive restart/export as applicable, without raw keys/content
   in routine logs. State/write failures do not turn rejection into publication.
9. Semantic unsupported-claim/completeness findings remain manual review outcomes;
   never present a negative repetition signal as a semantic pass.

## Completeness diagnostic

The private proposition-to-asset register combines exact source passages from
reviewed omissions with covered core propositions. It records local coverage,
full-source coverage, relevant asset fields and materiality separately using
Fully captured / Partially captured / Absent / Ambiguous. Rows may overlap and
are not a denominator for a completeness percentage. One proposition may span
assets and one asset may capture several related clauses; no one-to-one rule is
assumed. Text presence does not certify that an asset with another corrupted
field is fit for ordinary acceptance.

Recurring losses concern action-specific consent; owner/repairer/host authority;
qualification and supervision limits; method refusal/safety exceptions; accepted
handoff ownership; queue notices/privacy; measurement/feedback limits; and scope
of testing/warranties/expertise. A later chunk may supply complementary knowledge
without curing a local omission. Observation-versus-hypothesis materiality for
chunk001 remains qualified. No automatic completeness score or prompt change is
proposed.

## Recommended sequence and owner decisions

1. Preserve this characterization/design and the private integrity manifest.
2. Review proposed thresholds, extreme-quotation false positives and length-only
   diagnostics. Approve a corruption gate scope separately from semantic acceptance.
3. Implement the shared pre-settlement check plus generated/manual failure mapping,
   safe diagnostics and atomic-preservation tests, without touching schema/prompts.
4. Run focused and full offline suites, including allowance/503 and persistence
   paths; retain the frozen original results. No live retry of this evaluation.
5. Consider private rejected-payload retention and any additional length/symbol
   safeguards as explicit follow-up decisions. Evaluate omissions separately with
   human-labeled propositions, not a speculative automated sufficiency metric.

Outstanding owner decisions: gate scope including manual imports; threshold policy
and false-positive treatment; diagnostic-only versus blocking exceptional length;
private rejection-artifact retention; and approval of the newer full-source reviewer
judgments. This task authorizes design/tests only. No implementation or new provider
experiment has been performed or authorized here.

## Backward compatibility and observed offline results

The proposed gate applies to new extraction settlements only. Existing snapshots,
accepted assets, exports and revision evidence remain readable without being
revalidated, cleaned or silently invalidated on load. A retrospective audit can
report suspect legacy content without rewriting it. Previously accepted active
assets must survive a rejected replacement; this is distinct from endorsing old
corrupt content. No model/schema migration, provider contract change or historical
rewrite is needed. Saved-output snapshots remain immutable.

The field probe does not catch every degenerate representation: word periods
longer than 32, corruption spread across many individually short list items,
fluent unsupported assertions and long symbol-only blobs require separate study.
A negative result must never be displayed as proof of coherence or source fidelity.

Validation recorded for this design:

- 23 new offline characterization/probe tests passed.
- 59 focused tests passed including existing extraction-validation diagnostics,
  batch handling and allowance/confirmed-503 controls.
- Two existing dependency deprecation warnings remain.
- A read-only pass over all 25 retained assets flags only the observed bad
  explanation: 2,160 adjacent periodic words, period 15, 144 complete cycles,
  periodic fraction 0.950704. This is an observed example, not a population-level
  false-positive/false-negative estimate.
- The separate coverage register has 52 overlapping diagnostic rows (core claims
  plus scoped reviewed omissions). It is not a sentence census, completeness score
  or claim that 52 distinct assets should exist.
- Original evaluation, four backups, prior reviews, owner records and the local
  acceptance database were fingerprinted: 74 protected files unchanged.
- No application behavior changed. New tests/design/probe are uncommitted; no
  private evidence is included in them. No Gemini or hosted operations occurred.
