# Measuring Narrative Engagement — incident reconstruction investigation

Investigation date: 2026-10-24. Baseline:
[requirement-to-implementation review](traceability-review-2026-10-21.md).
Worktree: `feature/knowledge-assets`, HEAD `95c8f652045a342c315c4c20b884e5c599d76403`,
including its preserved uncommitted implementation.

**Result: the original incident records were not recovered after an exhaustive
reasonable search of the available project records. Historical root cause and
whether the current system prevents that particular failure remain undecidable.**
This is an investigation outcome, not incident closure or release approval.
No product behavior, tests, historical artifacts or existing reports were changed.

## Evidence classes and confidence

- **Historical primary evidence:** source bytes, actual request, runtime capture,
  response, saved output or display from the original incident. None recovered.
- **Historical secondary evidence:** prior descriptions of an observation. The
  user's incident reference and older sanitized KE-PQ-002 synopsis are available;
  the latter describes a different case and cannot identify this incident.
- **Later reproduction:** deliberately synthetic assets, mocked answers and
  regression logs. These establish mechanisms and current safeguards only.
- **Inference:** a technically possible explanation without the original chain.

Confidence is **high** for directly inspected files/test outcomes within the
stated search boundary, **conditional** for protection of a specified input
pattern, and **unknown** for historical causation. Negative search results do not
establish absence from hosted storage, another machine, another browser or backups.

## Search performed and evidence located

Before investigation, an external SHA-256 manifest recorded all **284** tracked
and nonignored untracked files. No branch checkout, reset, stash, staging or
historical artifact edit was performed.

| Search area | Method and result | Evidence class / confidence |
| --- | --- | --- |
| Current repository, acceptance records, documentation, tests and scripts | Case-insensitive searches for the exact title, narrative engagement and contamination. The exact title appears in the traceability review and the explicitly synthetic integrity fixture. Broader narrative matches are synthetic relevance/browser fixtures. Persistence tests' generic contamination wording is unrelated. | Later reproduction / high. No original incident capture found. |
| Both available worktrees and external project files | Content/file inventory scanned 670 files under `/workspace`, excluding Git internals, dependency/cache trees and credential/session directories. Shared, scratch and library-files directories are empty. The inventory includes validation reports, existing logs and the offline baseline archive. No source/output capture of this incident was found. | Direct search observation / high within this boundary. |
| Local storage, ignored material and exports | This worktree has no `apps/api/storage`; the original checkout has three related upload/extracted/chunk files, no database. Their contents have no incident title, narrative-engagement phrase or old export identifier. No local saved-output database, backup, archive or original incident export was located. Source bodies remain private and are not reproduced here. | Direct search observation / high. Lack of a title match alone cannot exclude a renamed or unidentified record. |
| Binary project material | The three available PDF copies are byte-identical copies of the legacy *Made to Stick* source. Text extraction found neither the incident title, narrative-engagement phrase nor the older export ID. No archive/SQLite candidate was found by signature in the scanned files. | Direct search observation / high. This does not establish the incident's actual bibliography. |
| Git history | Repository is not shallow. Searched all 377 commits reachable from available local/remote-tracking refs, commit messages, changed text and historical path names. No incident-title/narrative-engagement/contamination change was found. Reflogs and stash inventory provide no incident capture; read-only `git fsck --no-reflogs --unreachable` reported no additional unreachable objects. | Direct history inspection / high for available objects, not all possible remote/deleted branches. |
| GitHub project records | Repository-scoped code search for `"Measuring Narrative Engagement"`; issue searches for `narrative`, `contamination`, `KE-PQ-002`; PR searches for `narrative`, `KE-PQ-002`. All returned empty results without tool errors. Code search covers the default branch; the local feature history was searched separately. | Negative remote search / conditional on search/index/access coverage. |
| Original KE-PQ-002 baseline | Commit `d77e95a` records a sanitized synopsis of `output_2960048d.md`; `3f74cb0` implements precise member citation accounting. Neither identifies Measuring Narrative Engagement. The private export bytes referenced by the synopsis are absent here. | Historical secondary evidence / high for what the synopsis says; no proven relation to this incident. |
| Earlier integrity review logs | `integrity-review-before.log` records eight failing synthetic probes and one passing characterization. Current tests use a material named “Measuring Narrative Engagement — synthetic test only.” Neither is a historical response. | Later reproduction / high. The shared name is not evidence of authenticity. |
| User-observed creator discovery | The conversation reports the creator question, three selected libraries, 35 results and examples of rankings/overlaps. It supplies no source/asset/output identifiers or incident capture tying those observations to the contamination event. | User-reported secondary evidence; incident linkage unknown. |

Search inventories, hashes and current test logs are retained outside Git at
`/workspace/ke-pq-002-validation/incident-*`. They contain paths/technical metadata,
not a reconstructed private source. The earlier `private-source-inventory.json`
contains searched term labels; those labels are not recovered source findings.

No hosted database/storage location or original record IDs were supplied. This
investigation did not guess credentials, inspect credential files, enumerate
unrelated personal accounts, access a live research store or contact a model.
The managed runtime reported no configured secrets/outbound identities. This
does not prove that a separately configured deployment has no records.

## Reconstructed timeline: what can actually be dated

| Time / event | Recoverable fact | Limit |
| --- | --- | --- |
| Original Measuring Narrative Engagement event — unknown time | User reports an incident requiring single-source evidence-integrity investigation. | No original timestamp, build, task, source identity or output recovered. |
| 2026-10-18 19:57:22 UTC — separate export | The older synopsis records this timestamp for a Create research-synthesis export and four applied references. | The synopsis is available; the original export is not. It is not established as this incident. |
| 2026-10-18 — baseline/accounting commits | `d77e95a` preserves KE-PQ-002 observations; `3f74cb0` corrects citation accounting. | These document a separate evidence chain and general safeguards. |
| Creator discovery report — undated in available record | The user reports the creator question and Marketing, Storytelling & Audience Psychology, Creator Strategy & Social Platforms scope. | Do not transplant this query/scope into an invented incident request. |
| 2026-10-20/21 continuation and integrity review | Synthetic relevance evaluation, scope rejection, interpretation transport and display protections were implemented and tested. | Later diagnostic work; it does not establish which code produced the incident. |
| 2026-10-24 — current investigation | Broader repository/history/storage/project-record search and focused current regression replay. | No historical primary evidence recovered. |

## Original data flow: recovered versus missing

| Incident stage | Recovered evidence | Missing evidence / effect on conclusion |
| --- | --- | --- |
| Source/materials | Reported material title only. | Exact source/library IDs, author/version, original text, chunks, manifest, extraction jobs and active asset records. Cannot verify content ownership, contamination during import/extraction, or even exact selected scope. |
| User query/task | No incident-specific request. Creator discovery question is a separate reported observation. | Mode, original question, constraints, selected source/asset IDs, limit, request time and running build. Cannot reproduce its retrieval. |
| Retrieval and ranking | No historical candidate or diagnostic capture. | Candidate IDs, matched fields/terms, scores, ordering and exclusions. Cannot establish lexical misses, imported foreign evidence or actual rank displacement. |
| Selected evidence | No original selection or retained groups. | Explicit choices, canonical/member IDs, result-limit outcomes and independent material membership. Cannot decide which findings should have reached preparation. |
| Preparation/transformation | No original snapshot/token or compact model input. | Member statements, quotations, chunk/source identities and synthesis-context associations before/after compaction. Cannot locate a historical loss or scope breach. |
| Generation | No original response or saved-output record. | Model/version, exact supplied context, response, structured citations and validation outcome. Cannot distinguish unavailable, unretrieved, untransported, supplied-but-omitted or fabricated content. |
| Citation/provenance display | No original screenshot, rendered text, export or citation payload. | Exact reference IDs, source-info lookup and snapshot. Cannot establish whether metadata was correct but display binding was wrong. |
| Expected versus observed | Current instruction requires source isolation and faithful use of available evidence. | Original disputed claim/quotation, foreign material, expected finding and observed output are not supplied. No claim-level comparison can be made. |

An unavailable **incident record** does not imply an unavailable **research
finding**. Conversely, an available synthetic finding does not prove that the
same finding existed in the original selected material.

## Candidate mechanisms mapped to current safeguards

Every historical-cause conclusion below remains **unknown**. A passing protection
test means the specified representation is rejected/preserved now; it cannot
establish that the incident had that representation.

| Candidate mechanism | Available evidence | Current-system disposition / confidence |
| --- | --- | --- |
| Upstream content or interpretation consistently mislabeled as belonging to the selected material | No original source/chunks/assets. Identity metadata may be internally consistent while text is wrong. | **Not proven prevented.** Known valid manifests check chunk ownership; identity checks do not establish semantic faithfulness or detect every consistently mislabeled historical record. Conditional guard coverage; historical cause unknown. |
| Retrieval adapter returns an unselected material | Prior synthetic wrong-scope adapter probe; no original retrieval. | **Specified pattern prevented:** local/indexed scope checks reject with 409 before provider dispatch. High confidence for tested paths. |
| Canonical/member/trail/group/synthesis context disagrees about source identity | Prior synthetic mutation probes; no original prepared state. | **Specified patterns prevented:** generation revalidates representations, member identity and known chunk manifests. Ambiguous multi-source membership cannot authorize generation. High confidence for tested paths. |
| Consolidation groups conceptually distinct findings with similar wording | No incident members or source passages. Current grouping is lexical and conservative, not semantic equivalence. | **Only partly protected:** member provenance/interpretations remain traceable; grouping itself does not prove equivalence. Out-of-scope identity is rejected, but a false conceptual merge within valid scope remains possible. |
| Result limits or Find/Ask differences exclude a useful idea | Existing synthetic relevance tests and inspected separate Ask retrieval; no incident selection. | **Partial:** explicit selected IDs must survive or reject. Ordinary ranking limits and Ask's fresh eight-group retrieval can still omit available findings. |
| Noncanonical interpretation disappears during compaction | Earlier synthetic reproduction; no original incident context. | **Transport corrected for newly prepared groups:** member interpretation stays with its own ID and quote. Existing saved snapshots are not backfilled. High confidence for tested transport, unknown historical relevance. |
| Generator omits a dimension despite receiving evidence, or makes an unsupported interpretation using valid IDs | Fake response can omit trust while receiving curiosity and trust. No original response. | **Not generally prevented:** exact citations do not prove semantic coverage or entailment. This is characterization, not a repaired sufficiency failure. |
| Renderer aliases an unknown reference to the selected material or displays a foreign member quote as its support | Prior synthetic source-prefix/member-display regression; no incident display. | **Specified defects prevented:** full/exact unambiguous legacy identity binding and scoped member disclosure. High confidence for tests; actual incident binding unknown. |
| Citation accounting credits all sources in a group for one cited member | Historical accounting code and synthetic member tests, no incident reference list. | **Exact-member accounting corrected**, independently of this investigation. Does not prove historical count inflation occurred here or establish independent studies. |

### Mechanisms ruled out

**No candidate historical root cause can responsibly be ruled out** without the
source, request and observed output. The search only rules out treating the
located synthetic fixture/logs as original records: their code explicitly creates
synthetic sources and fake responses. It also establishes that the older export
synopsis does not identify this incident; a relationship cannot be asserted.

No new provider call is necessary or justified. A new answer would be a new
reproduction and would not recover missing historical inputs or output.

## Smallest defensible surrogate and exact regression protection

There is **no recovered incident-specific assertion** strong enough to justify a
new original-incident golden test. Preserve the existing synthetic suite; do not
copy the reported title into a new fixture and call it recovered evidence.

The minimal surrogate is two strict-model synthetic assets from sources A/B,
with A selected and B unselected. Inject B at the retrieval boundary; then mutate
one prepared representation at a time. Expected result: explicit 409, zero fake
provider calls at generation, no saved output or snapshot mutation. Separately,
an unknown reference must not borrow A's title/quote in rendering. This tests the
reported class of concern without presuming its historical cause. The existing
tests already provide these checks, so no new behavioral change or fixture is
required now.

| Exact existing test / module | Defensible conclusion |
| --- | --- |
| `test_ke_pq_002_integrity_review.py::test_single_source_retrieval_rejects_a_backend_scope_violation` | Local adapter contamination surrogate rejects before preparation completes. |
| `test_ke_pq_002_integrity_review.py::test_single_source_indexed_adapter_cannot_widen_scope[list/search]` | Indexed adapters cannot widen declared source scope. |
| `test_ke_pq_002_integrity_review.py::test_prepared_source_contamination_fails_before_provider` | Eight canonical/trail/group/context/member/chunk mutations reject without dispatch, output creation or mutation. |
| `test_ke_pq_002_integrity_review.py::test_declared_source_cannot_borrow_another_sources_known_chunk` | Known source manifests expose a borrowed chunk at retrieval/generation boundaries. |
| `test_ke_pq_002_integrity_review.py::test_noncanonical_interpretation_reaches_context_without_relabeling_its_evidence` | Distinct member interpretation transport is preserved, without changing its quote. |
| `test_ke_pq_002_integrity_review.py::test_available_dimension_can_be_omitted_after_its_evidence_reaches_provider` | Remaining omission limitation is visible; a pass does **not** mean coverage is fixed. |
| `answer-renderer.test.mjs`: “unknown longer source IDs cannot borrow a selected source prefix or evidence”; “member evidence outside the provided material scope is not displayed as support” | Display surrogate prevents false source binding. |
| `test_relevance_evaluation.py` | Existing supported creator variants, scope, independent member retention and explicit unresolved vocabulary boundary remain unchanged. Synthetic independence labels are not bibliographic findings. |

Current focused verification: **43 backend tests passed, 0 failed**, two existing
dependency deprecation warnings; **13 renderer tests passed, 0 failed**. The four
supported creator variants retain their existing **8/8** expected direct-finding
appearances; the vocabulary-changing case remains **0/2**. No new relevance or
historical-reproduction success is claimed. Earlier complete-suite counts remain
the prior review checkpoint, not a newly run complete suite.

```sh
.venv/bin/python -m pytest apps/api/tests/test_ke_pq_002_integrity_review.py apps/api/tests/test_relevance_evaluation.py -q -o faulthandler_timeout=30
node --test --test-isolation=none apps/web/tests/answer-renderer.test.mjs
```

The first backend invocation stalled at the local TestClient case under restricted
socket access and was terminated. The complete focused run above passed with
loopback permission; this was not a product-test failure or a provider call.
All generation responses are fakes. No Gemini call, paid service, repair call or
additional model request was made.

## Remaining unknowns and recovery gate

The smallest useful recovery package is an **existing original saved output or
export/display capture**, its **exact selected material IDs and request**, and the
corresponding **source text plus active asset/member/chunk records**. These would
anchor expected-versus-observed claims and scope. Add the original prepared or
provider-context capture if available to distinguish retrieval/preparation loss
from generation omission. Include deployment build/revision and timestamps;
current uncommitted code does not establish the code that served the incident.
Preserve original bytes privately; never force-add them to Git.

Final preservation audit: all **284** pre-existing tracked/nonignored untracked
files are byte-identical to investigation start, HEAD is unchanged, staging is
empty, and the original checkout remains clean. The only new repository file is
this report. `git diff --check` passes; validation/search logs remain outside Git.

Without those records, the following claims remain unverifiable: which source
was contaminated; what foreign or unsupported finding appeared; whether a
relevant finding was available; which stage introduced or dropped it; exact
ranking/selection; whether citations or only display were wrong; and whether the
current system fixes that event completely. This uncertainty cannot be resolved
by selecting one plausible mechanism or generating a fresh answer.

**Stop here before new behavioral implementation.** The incident investigation is
complete for available evidence, while incident resolution remains blocked. The
planned next order remains capacity/resource validation, actual creator-case
replay, dimension coverage, evidence fidelity, continuity, and only then a decision
on further research-intelligence behavior. No commit, push or deployment occurred.
