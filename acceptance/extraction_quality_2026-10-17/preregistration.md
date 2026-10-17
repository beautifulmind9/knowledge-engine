# Extraction-quality acceptance preregistration

**Status:** Preregistered; no extraction, retrieval, or Workshop result has been inspected.  
**Run date:** 2026-10-17 (source authored; execution pending approved runtime access).  
**Build baseline:** `feature/knowledge-assets` at `6492e55c81c842bf823666e4330a86559d2eb7a7`.  
**Source:** `source.md`, title “Running a Community Repair Session: A Field Guide for Volunteer Hosts.”  
**Source SHA-256:** `93afffd120832c93694a2e854e4a8dd444e0d1f83bc05d812ab7d49390485de8`.  
**Source size:** 3,286 whitespace-delimited words; 20,145 UTF-8 bytes.  
**Expected default chunking:** 1,200-word window / 200-word overlap gives four chunks (1,200; 1,200; 1,200; 286 words). Final chunk IDs and exact uploaded chunk text must still be exported from the application and compared against this source after processing.  
**Rights:** Original synthetic material authored for this evaluation; no external text or copyrighted source is included.

## Frozen scoring rubric

Score each applicable dimension 0–2. Do not change criteria after seeing results.

| Dimension | 0 — Fail | 1 — Needs revision | 2 — Pass |
|---|---|---|---|
| Grounding | Claim conflicts with or is unsupported by source | Mostly supported but wording stretches source | Fully supported by cited passage(s) |
| Completeness | Omits an important condition or idea needed to preserve meaning | Captures core idea but misses a useful qualifier | Captures the reusable idea and material qualifiers |
| Granularity | Several unrelated ideas collapsed or one idea fragmented into unusable pieces | Some over/under-splitting | One coherent reusable idea at useful scope |
| Duplication | Redundant asset without distinct value | Partial duplication or unclear distinction | Distinct from other assets or justified repetition |
| Asset type | Type materially misclassifies the knowledge | Type is plausible but not the best fit | Type accurately represents the content |
| Presentation | Title/summary depends on hidden context or misleads | Understandable with some source context | Clear and useful outside the paragraph |
| Evidence precision | Evidence absent, inaccurate, or too broad to support claim | Evidence supports claim but is imprecise | Exact sufficient source evidence is attached |
| Provenance | Source/chunk/job/generation/version linkage is wrong | Provenance is incomplete but recoverable | Every available linkage is correct |
| Transferability | Overgeneralizes or is unusable outside the chunk | Transfer requires a qualification | Reusable with source scope and limits intact |

Critical failures override numeric scores: fabricated factual claim, incorrect evidence, incorrect provenance, or materially omitted important idea.

## Empty-output classifications

- **PASS — EMPTY APPROPRIATE:** the exact chunk contains no independently useful reusable concept, method, rule, example, condition, exception, warning, limitation, or comparison.
- **FAIL — MATERIAL OMISSION:** the exact chunk contains important reusable knowledge that should have yielded at least one asset.
- **REVIEW — AMBIGUOUS:** reasonable reviewers could disagree about whether an idea merits a standalone asset.

Every zero-asset chunk will be read in full and judged on its own text. Immediate neighbors will be consulted only to classify boundary effects, repetition, or capture elsewhere; a loosely related neighboring asset will not excuse a local omission.

## Frozen retrieval questions and labels

Questions are fixed before extraction or retrieval. Labels define what a useful result must support; no retrieval result has been inspected.

| ID | Question | Relevant source concepts expected | Type |
|---|---|---|---|
| R1 | What decisions does triage make, and how is that different from choosing which accepted item goes next? | Triage vs. queue prioritization; safety/feasibility vs. order among accepted work | Broad understanding |
| R2 | What are the separate purposes of an intake ticket, diagnosis card, and parts note? | Three records and their distinct functions/limits | Exact concept |
| R3 | How does summarize-and-re-enter differ from permission-to-redirect? | Shared-map recovery vs. negotiated topic transition; distinct triggers and steps | Related-method distinction |
| R4 | When should a repair stop, and what does the guide say about uncertain part compatibility? | Stop conditions; possible-match labeling; no promise before verification | Caveat/exception |
| R5 | What is the best way to tune a guitar before a performance? | No relevant source material | Deliberately irrelevant |

Retrieval review records relevant assets returned/missed, false positives, ordering against the source-backed labels, and whether evidence supports each answer.

## Frozen chunk and asset review sampling rules

1. Review every zero-output chunk.
2. Review all chunks tied for the lowest non-zero asset count until at least two are covered, if available.
3. Review chunks immediately before and after every zero-output chunk.
4. Review the two highest-output chunks (or all if fewer than two).
5. Review chunks covering the two attention-recovery methods and at least one example/caveat.
6. Select three ordinary chunks using a reproducible pseudo-random selection: sort chunk IDs lexicographically, seed `20261017`, and select distinct indices generated by Python `random.Random(20261017)`.
7. If categories overlap, review once and record all reasons for inclusion.

For each reviewed chunk, inspect every asset returned for it and score the nine dimensions. Record examples and critical failures individually; do not reduce the acceptance decision to a mean.

## Execution protocol to preserve

- Use the current production/default Gemini configuration and current strict validation.
- Submit one chunk per provider request, retaining the current retry behavior and free-tier/allowance gates.
- Do not edit prompts, add repair/fallback, or suppress valid empty responses.
- Before any provider request, confirm the approved runtime has a ready credential, the default model, free-tier confirmation, and remaining allowance. Never print the credential or request headers.
- Record every attempt/result/failure and timestamp; no provider retries beyond existing application policy.
- Workshop generation is a separate provider operation and must follow the same approved free-tier and allowance policy.

## Required retained audit record

The final WSG-independent audit export must include the exact source bytes and SHA-256; workspace/library/source IDs; every chunk ID, ordinal, exact text, length and structural metadata; every job ID, chunk link, status, generation, extraction version, provider/model/result metadata and timestamps; every asset ID and complete validated payload with source/chunk/job/generation/version/lifecycle/ordinal/evidence provenance; all zero-output decisions and sample scores; retrieval questions/results; and saved Workshop output IDs, evidence snapshots, revision/compare data and relevant provenance. Export only this acceptance source's records.

## Run status

Execution is pending because the current managed environment has no configured runtime secrets or variables and its enforced network allowlist does not permit the Gemini API. No provider request has been made. This is an execution blocker, not an extraction-quality result.
