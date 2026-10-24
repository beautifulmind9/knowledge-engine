# KE-PQ-002 Phase D — prospective retrieval quality and diagnostics

Date: 2026-10-24. Evidence baseline:
[Measuring Narrative Engagement incident investigation](measuring-narrative-engagement-investigation-2026-10-24.md).

This phase is prospective and synthetic. It does not reconstruct the original
incident or claim that incident is resolved. It changes no generation, research
sufficiency, KnowledgeAsset schema, citation, grounding, extraction or source
integrity behavior. No provider was called.

## Working-tree reconciliation

The implementation began on `feature/knowledge-assets` at
`95c8f652045a342c315c4c20b884e5c599d76403`, preserving the existing staged,
unstaged and untracked KE-PQ-002 work. Staging was empty. A SHA-256 inventory of
the relevant existing files was saved outside Git at
`/workspace/ke-pq-002-validation/phase-d-start.sha256`. The separate
`/workspace/knowledge-engine` worktree remained clean on `work` and was not
modified.

## Diagnostic baseline and changes

The existing opt-in `RetrievalDiagnostics` collector already captured most of
the required evidence without routine source text: query hash/length, selected
library/material/asset IDs, candidate asset/source/chunk IDs, scores, original
matched terms, allowlisted score contributions, pre/post-consolidation positions,
exclusion reasons, result-limit retention, provenance IDs and preparation facts.
It performs no I/O and is not exposed as an HTTP endpoint.

Phase D adds two explicit details:

1. Find diagnostics now resolve a selected library to its exact source IDs, so a
   trace records the effective material boundary as well as the library ID.
2. Schema version 2 adds `final_selection`, an ordered list of canonical/member
   asset IDs and source IDs actually selected after consolidation and limits.

Plural normalization records both the original request term and the matched
variant, for example `narratives` → `narrative`. Default diagnostics still omit
request text, titles, evidence excerpts, interpretations and source bodies.
Full request text remains an explicit local opt-in. Opaque IDs and matched terms
can themselves be sensitive; real captures must stay in private local storage.

Diagnostic exclusions are factual pipeline outcomes, not relevance judgments.
Preparation state is not evidence quality. A positive lexical score does not
prove applicability, entailment, independence, research quality or sufficiency.

## Failure investigation

The prior offline trace showed the vocabulary-changing creator question produced
zero candidates in both Find and Workshop. For the two labeled direct assets,
every candidate record had score 0, no matched terms and
`no_query_overlap`. Scope was preserved, so source widening, consolidation and
result limits were not the cause. Failure occurred during lexical admission.

The query uses `narratives` and `personalities`; the relevant synthetic assets use
the singular terms `narrative` and `personality`. This supports a small lexical
normalization. It does not support topic-specific mappings such as followers →
audience, information gaps → curiosity or identification → engagement.

## Narrow implementation

`lexical_variants()` returns the original token and at most one conservative
English plural stem:

- words ending in `ies` map to singular `y`;
- other sufficiently long words ending in `s` drop the final `s`, excluding
  `ss`, `us` and `is` endings.

Find and Workshop use the same variants while retaining the original query term
for scoring/accounting. The indexed candidate adapter receives the variants too;
otherwise the application scorer could never recover an asset omitted by indexed
acquisition. No synonym list, embedding, semantic classifier, threshold or extra
service was added.

## Offline evaluation

The retained `research_cases.json` fixture was not rewritten. The earlier trace
is `/workspace/ke-pq-002-validation/phase-d-before.json`; the current trace is
`phase-d-after.json`. Both contain only synthetic fixture data.

| Evaluation | Before | After |
| --- | ---: | ---: |
| Four supported creator variants, Find direct-finding appearances | 8/8 | 8/8 |
| Vocabulary-changing creator case, Find | 0/2 | 2/2 |
| Vocabulary-changing creator case, Workshop | 0/2 | 2/2 |
| Exact selected scope across nine retained cases | 9/9 | 9/9 |
| Semantic-only held-out paraphrase | not recorded | 0/2 |

Only the vocabulary-boundary case changes in the retained nine-case report.
Its Find order becomes `creator_study`, `narrative_measure`, `distinct_measure`,
`writing_advice`; Workshop contains the same four ideas in a slightly different
order. Diagnostics attribute the direct matches only to the plural variants:

- `creator_study`: `narratives`→`narrative` in title and
  `personalities`→`personality` in evidence;
- `narrative_measure`: both variants match evidence; its independent member and
  provenance remain consolidated and traceable.

The held-out question “How do stories and suspense help public figures form
enduring bonds with their communities?” still retrieves neither labeled direct
finding. This is the current semantic-vocabulary boundary. Phase D does not count
the 2/2 inflection result as semantic retrieval or research sufficiency.

## Tests

New/extended regressions verify:

- diagnostics expose ordered final selection and resolved source scope without
  copying private text;
- original terms and matched variants remain inspectable;
- local Find and Workshop recover the two direct assets through inflection only;
- indexed acquisition receives identical bounded variants and exact source IDs;
- the semantic-only paraphrase remains outside lexical acceptance claims;
- all earlier relevance, consolidation, scope and 8/8 creator cases remain stable.

Results:

| Suite | Result |
| --- | --- |
| Focused diagnostics and relevance | 33 passed, 0 failed |
| Focused diagnostics, relevance, consolidation and coverage | 44 passed, 0 failed |
| Complete backend | 1,227 passed, 0 failed; two existing dependency deprecation warnings |
| Complete frontend | 207 passed, 0 failed |
| `git diff --check` | passed |

All tests are offline. Backend provider behavior uses existing fakes/transports;
no Gemini credentials or calls were used. There was no paid service, retry,
repair call, migration, commit, push or deployment.

## Remaining limitations and next-phase decision

- Morphological normalization is intentionally asymmetric: it helps plural query
  terms meet singular source terms. It is not a general English stemmer and will
  miss irregular forms and singular-query/plural-source cases.
- Indexed backends can return only candidates their own lexical acquisition
  admits. Passing the same variants closes the tested gap, but backend-specific
  tokenization still requires contract validation.
- Diagnostics explain deterministic ranking mechanics, not whether a result is
  truly direct, transferable or incidental. Human labels remain external.
- Semantic-only paraphrases remain unresolved at 0/2. No synonym expansion is
  justified from one creator fixture, especially topic-specific equivalences.
- The historical ranking/duplicate reports and Measuring Narrative Engagement
  incident remain unverifiable without their original records.
- Answer dimension coverage, evidence fidelity and discovery-to-application use
  remain later phases. Retrieval success does not establish that generation will
  use the evidence.

The results justify proceeding to the planned **capacity/resource validation**
phase: diagnostics are sufficient to observe candidate admission and final
selection, the narrow lexical defect improved without regression, and all suites
pass. They do **not** justify semantic retrieval, automated sufficiency or a claim
that KE-PQ-002 research intelligence is complete.

Stop before commit, push or deployment.
