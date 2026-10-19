# Extraction completeness candidate — proposed preregistration

Recorded UTC: 2026-10-19T02:51:25.968029+00:00

Status: Candidate 1 three-rule prompt accepted by owner for controlled evaluation;
recorded before execution. Evaluation setup, disputed labels and real-model
execution remain subject to separate owner authorization. This is a separate comparison, not an amendment to
frozen KE-PQ-001. No provider request is authorized by this document.

## Frozen comparison inputs

- Control code baseline: `74cb1d7486c77831ed8cf29ab961e00b0170c54a` with its committed integrity safeguard.
- Control instructions SHA-256 (UTF-8): `a9a7e8a713ae09b2c81bdc4ca58c0fd969b16a42083da70869962e1805031de5`.
- Candidate instructions SHA-256 (UTF-8): `a10ffe329c9ff44edd083c361b7917a445ac998038df9141ef9ccafae4e29bc1`.
- Held-out source/label bundle SHA-256: `054f683e4fb7cac402f5123048f9125dff7ce9ae8bd5f43eae46eea22c12e183`.
- Frozen source SHA-256: `93afffd120832c93694a2e854e4a8dd444e0d1f83bc05d812ab7d49390485de8`.
- Frozen preregistration SHA-256: `5eab85f12be0f8d827b44b26015d8051ad0e168a4fdd5f67e730f2c5a86dd4b3`.
- Frozen original single-chunk schema contract SHA-256 (retained record):
  `718b3c7bde228f4a61c8cd854a977c7258f036b05662fa49d3334a9060f6284d`.

Before execution, freeze reviewed candidate code, exact schemas/SDK versions,
inputs, labels, run order and reviewer decisions in a timestamped supplement.
Any prompt/input/criteria revision requires a new version before results are seen.
The original source, rubric, assets, decisions, execution markers and backups
remain unchanged. Do not reset or reuse any original execution runner/marker.

Historical extraction code baseline: `3f74cb00d5da5c74cf9e75900d040900a0e45753`.
Candidate 1 version: the focused commit containing this preregistration and the
exact candidate prompt fingerprint above, based on control commit `74cb1d7`.
Record its full resulting commit SHA in the execution supplement; the document
cannot embed its own containing commit SHA. Semantic improvement is unconfirmed.

## Exact text fingerprints

All following hashes cover UTF-8 text only, without an added trailing newline.
The bundle hash above additionally covers evaluator labels and JSON formatting.


- Frozen window 1: words [0, 1200), 1200 words, SHA-256 `6b058ec2e4a20e12ac33d0ece0c0f5c271ab6de5e39221ef3a9c2282b78211b9`.
- Frozen window 2: words [1000, 2200), 1200 words, SHA-256 `649bdf8451ac0de06ad6b6289bd216025da5b39961937f61b3f2ec41fcc6a032`.
- Frozen window 3: words [2000, 3200), 1200 words, SHA-256 `52601177f075ac490d94b45c66961d4a61a2e3c502907e5e7cbd9854cb2ba86e`.
- Frozen window 4: words [3000, 3286), 286 words, SHA-256 `1e05447fdea4c073d145d61ea822866efee4c04fd2476b2179346e4b55f8fc40`.
- Held-out `archive-access`: SHA-256 `900def999595886770ff55370b384c869fdcdda493d9d7b44875fe6f6f52648d`; 4 predefined evaluator targets.
- Held-out `field-observations`: SHA-256 `b9a1bfab7d870ba0d98bb56fed1d9d004293d7f7e2bd46a3cc0ce66eac5faa40`; 5 predefined evaluator targets.
- Held-out `community-rehearsal`: SHA-256 `b82ec3fb8b44519c52bc00fddfdd2a9e71ee6cd6a9125707331a3002907d0217`; 5 predefined evaluator targets.

The original window word ranges are zero-based, end-exclusive. Their exact text
is retained in the ignored original request contracts; do not copy private runtime
exports into Git. Recreate windows deterministically from the committed synthetic
source and verify these hashes. The three held-out texts and their expected
propositions are fixed in held-out-sources.json before provider execution.
Targets may map many-to-many to assets; they are not asset-count requirements.
Disputed materiality remains explicit and is not silently adjudicated here.

## Candidate and smallest intervention

Only instructions 1, 9 and 15 change. Remove count-oriented selection pressure; retain
material source-supported conditions, exceptions, authority, responsibility
acceptance and safety limits; distinguish applicability limits from incidental
publication disclaimers. Group coherently without hiding independent rules or
creating duplicates. Optional fields remain conditional. All other instructions,
models, schemas, grounding, gateway, free-tier gates, accounting and retries stay.
This implements Capture naturally / Structure invisibly / Confirm visually without
requiring users to enumerate propositions or introducing automatic semantic scores.

## Separate storage and execution controls

Proposed root: `storage/acceptance-completeness-candidate/run-001/`, separate from
all original acceptance storage. Do not create or start it now. Before any future
run, verify owner-only permissions, Git ignore, separate live storage/audit/exports,
port 8002 availability, one worker, local persistence and timestamped safe capture.
Never use the baseline live database. Keys remain interactive environment secrets.

Use the approved unchanged model `gemini-3.5-flash-lite`; owner must reconfirm
Free Tier/billing-disabled status, credential readiness, current quota, zero
unexpected candidate attempts and the existing 450-attempt gate at execution time.
Use the existing extraction API/gateway; no manual provider bypass or repair.
Hold schemas, source windows, integrity gate and generation settings constant.
Validate the actual serialized provider contract and fingerprints before dispatch.

## Comparison arms and order

A. Historical-source comparison: candidate-only extraction of the exact four
original windows, copied from the verified frozen source with unchanged 1,200-word
size/200-word overlap. Use new library/source/chunk/job IDs with explicit links
back to baseline window indices. Verify text/hash/length equality before dispatch.
Compare against the retained 25 original payloads and existing 52-row coverage
register. Do not rerun or alter the original frozen jobs.

Important confound: historical extraction predates the integrity gate. Report
prompt-only semantic comparisons separately from this gate difference. A candidate
integrity rejection is a terminal technical result, not an empty semantic pass or
proof of better completeness. Preserve safe diagnostics, do not bypass the gate,
and do not call this arm a strict controlled causal experiment.

B. Held-out paired comparison: use the three original synthetic texts in
held-out-sources.json, one unchanged chunk each. Review targets are evaluator-only
and never sent to the provider. They are prospective hold-outs, not a hidden or
statistically representative benchmark. Do not tune the prompt on their outputs.

Run both control and candidate using the same code baseline, integrity gate,
model, source text and schemas; vary only the instruction string. A reviewed local
evaluation-only harness or isolated checkout must select exact hashed instructions
without adding a production prompt selector or changing gateway behavior. Its
implementation and provider execution need separate authorization.

Fixed order: archive-access control/candidate; field-observations candidate/control;
community-rehearsal control/candidate. Execute historical candidate windows 1–4
first. No sampling of best runs, no extra regeneration after seeing quality.

Proposed initial budget: four historical candidate requests plus six paired
held-out requests = 10 initial attempts. At most one identical retry per request,
only after confirmed HTTP 503 and normal allowance admission: theoretical maximum 20
attempts. No additional manual retries, replacement runs or other provider
operations are included. This is a proposed budget, not authorization. Stop for provider,
validation, integrity, allowance, provenance or audit failures; disclose incomplete
comparison arms and request review rather than replacing outputs automatically.
The permitted gateway HTTP 503 retry is part of the same operation; stop after its
terminal failure. Before/after each operation, capture allowance day/count, actual
gateway attempt events and timestamps; count every dispatch including retries.
Reconcile their deltas with the persisted allowance, allowing no unexplained
attempts or day rollover. Stop immediately on inconsistency. Do not estimate
attempts from successful jobs or asset counts.

## Review method and unchanged rubric

Before running, resolve/label which existing reviewer omission judgments are
owner-confirmed and which remain proposed. Preserve qualified observation versus
hypothesis and bounded-improvement disagreements; do not silently convert them
to approved labels. Freeze any hold-out materiality decisions before execution.

Review all candidate chunks and every returned asset, including valid empty
results and complete structured payloads. Apply the original nine dimensions
unchanged: Grounding, Completeness, Granularity, Duplication, Asset type,
Presentation, Evidence precision, Provenance, Transferability. Use the frozen 0–2
definitions and critical-failure overrides by reference; no new semantic score.

Map source propositions to assets many-to-many. Report full/partial/absent/ambiguous
coverage, changed qualifiers, authority, acceptance, exceptions and scope. Preserve
local versus source-wide coverage. Overlap cannot excuse a local omission. Do not
use the overlapping 52 diagnostic rows as a percentage denominator.

For held-outs, reviewers initially see randomized A/B labels (seed20261017) and
source/payloads with arm-identifying IDs masked; retain originals and unblind for
provenance review. Masking does not guarantee complete blinding. Review historical
comparisons with their known baseline status disclosed. Prefer independent human
review, record disagreements and obtain owner adjudication; model self-review is
not ground truth.

Separately assess newly unsupported assertions and changed modality, sufficient
precise evidence, needless duplicate assets, over-bundling and fragmentation.
Count assets only descriptively. Do not penalize grounding solely because a
source-supported claim has an incomplete attached excerpt: record evidence
precision and completeness separately. Text in evidence counts as retained text;
its accessibility/summary limitations remain separate review findings.

## Proposed success criteria and limits

A higher asset count is never evidence of success by itself. Require fewer
owner-adjudicated important omissions on the repair source, without new material
loss of previously captured knowledge. Require no new critical unsupported claim,
incorrect evidence or provenance, and no newly unacceptable duplication or
fragmentation (rubric 0). Report every important exception individually rather
than hiding it in a mean. Technical rejection/incomplete arms prevent a success
claim and do not authorize a retry.

Held-out paired results must show no new material omission or critical failure
relative to control, no unacceptable duplication/granularity regression, and
source-backed improvement before claiming any held-out benefit. Report neutral,
mixed and adverse outcomes, including potentially different source densities.

Outcome labels are defined before execution:
- IMPROVED: the repair-source improvement and all non-regression safeguards above
  hold, with complete records and adjudicated material labels. State separately
  whether held-out benefit, neutrality or no benefit was demonstrated.
- REGRESSIVE: new critical unsupported content/evidence/provenance, material loss
  of captured knowledge, or unacceptable duplication/granularity is established.
  Do not offset these with additional assets or other restored propositions.
- INCONCLUSIVE: incomplete/technically rejected runs, unresolved decisive labels,
  or mixed evidence prevents the improvement criteria being established.
- NO DEMONSTRATED IMPROVEMENT: complete comparable results are neutral and show
  no reduction in important omissions, without an established regression.

One paired sample per case is preliminary, not proof of reliable model compliance
or broad generalization. Repeated trials/expanded hold-outs require a new approved
budget and preregistration. Offline contract tests verify wording/compatibility
only; they cannot establish semantic improvement or owner semantic acceptance.

## Audit and owner decisions

Retain timestamps; code/prompt/source/schema hashes; exact chunk text and IDs;
job/model/status/attempt metadata; allowance changes; validated payloads; evidence
and available provenance; failures; rubric reviews/mappings/disagreements; exports
and verified backup. Use safe structured gateway logs, never credentials/headers.
If token usage, finish reason or raw provider output is unavailable, state that
limitation rather than inventing it. No additional raw-payload retention mechanism
is authorized here.

Candidate wording is owner-accepted. Owner decisions remain on label/materiality disputes,
comparison criteria, future harness and isolated setup, human reviewers and the
proposed 10-request budget. No live request, hosted operation or migration occurs
as part of preparing this proposal.
