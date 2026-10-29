# Architecture and research handoff

## Implemented, experimentally verified boundaries

- `experiments/source_first/prototype.py`: standalone versioned passage indexing using SQLite FTS5/BM25,
  optional fixture-declared aliases/fusion/section context, exact decoded-text spans and cache invalidation.
- `apps/api/app/services/source_search.py` and router: `GET /source-search`, original-query BM25 over
  scoped preserved extracted-text artifacts, bounded ranked exact passages, stable versioned IDs and neighbors.
  The application integration rebuilds an in-memory index per request; the standalone prototype's persisted
  index/cache behavior must not be attributed to the integration. No schema migration or AI extraction prerequisite.
- `source_context.py`: `GET /source-context`, `build_source_context`, `verify_snapshot`, `validate_citations`.
  Targeted mode preserves ranked hits before neighbors. Broad mode is single-source structural sampling,
  not semantic completeness. Fingerprinted packages retain question, scope, source/original hashes, exact
  character ranges, retrieval/selection roles, budgets/exclusions and unindexed-content diagnostics.
- `apps/web/source-search.js`: optional original-text preview; no generation or semantic-completeness claim.
- `source_answer.py`, `source_answer_transport.py`, model and gateway reference: local-only targeted answer,
  strict schema/exact citation checks, frozen GenerateContent representation, trusted count receipt,
  input policy 32,768 with 8,192 reserve (maximum count 24,576), output+thinking ceiling 4,096,
  usage reconciliation, shared persisted allowance and one confirmed-503 identical retry. No semantic repair.
  One-shot capability is scoped to exact request and durable intent; ordinary experimental API dispatch stays
  unauthorized. Private retained records/export/delete behavior requires app infrastructure absent here.

## Preserved measurements, not new production claims

Fixture SHA-256: `3c637e0043e56cb95e55c06fc446f0ae594463ec2ed2018d7b9c9da27b86b4ee`.
Three synthetic sources, 26 fixed queries, 22 positive queries. Prototype mean recall@10 86.4%,
binary nDCG@10 0.824; expansion/fusion do not improve recall. Integrated recall@10 86.4%, nDCG 0.831
(two tie-order changes, not demonstrated semantic improvement). Six designated omission probes retrieve
supporting paragraphs. Targeted context/whole-paragraph qualification recall 89.4% with additional text.
Unmapped assent/disassembly paraphrase remains a failure. Four lexical no-answer probes do not establish
reliable semantic abstention. Broad full-small-source coverage is not scalable completeness: capped-at-12
broad context mean passage recall is 58.3%; important passages remain missing.

Historical prototype-only synthetic performance at 1,000 page proxies / 300,000 words:
172.1 ms construction, 10,346,496-byte index, 27.0 ms BM25 p95, 27.3 ms context p95,
whole-process peak RSS 76,955,648 bytes. This is repetitive synthetic data, not real-document application
latency, a production SLO or a new measurement in this snapshot task.

Parser probes show flattened tables, lost image/caption relations and image-only PDF pages omitted from
text. Preserving a file is not interpreting its images. No OCR, semantic retrieval, embeddings or new parser
has been implemented by this snapshot. Exact citation identity is not entailment, sufficiency or truth.

Historical full-application results were 243 focused / 1,338 backend / 185 frontend passing; those suites
cannot be rerun from this deliberately partial repository. Only independently rerun snapshot tests are
reported in `docs/SNAPSHOT-VALIDATION.md`.

## Hybrid feasibility and integration gates

Reuse frozen lexical probes as a baseline, scope/version IDs, exact-span verification, context snapshots,
known failures, source-change invalidation and bounded admission. A semantic candidate arm requires
separate fixed labels and evaluation; neither embeddings nor rank fusion is justified by these results.
Compare per-query passage and qualification coverage, distractors, cross-source isolation and duplicates;
do not reward more assets or claim semantic completeness. Keep provenance checks independent of ranking.

The freshly observed upstream development ref was `7715717cb2e91e043104e9765017baa801a66344`.
It contains later retrieval diagnostics/normalization, candidate-capacity protections, accepted extraction
prompt restoration and gateway/export changes absent from the historical research base. Reconcile rather
than replace those implementations. Shared conflicts include app.js/UX, gateway, backup/export, persistence
and scope contracts. This is a preservation snapshot, never a merge target for wholesale product replacement.

Before integration: run full application backend/frontend suites against an owner-selected current baseline;
verify scope, capacity, source-version invalidation, saved-output compatibility, private backup/delete semantics,
provider budget/receipt identity and one-shot replay. Measure actual artifact-read/index rebuild latency and
hosted resource behavior separately. Any live model test needs fresh count evidence, explicit authorization,
confirmed Free Tier and unchanged allowance/retry controls. No current provider/model compatibility claim
is established by copying historical code. Real-user document retention requires separate approval.
