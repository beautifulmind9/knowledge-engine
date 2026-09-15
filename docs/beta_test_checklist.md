# v1 beta release decision and acceptance checklist

Date: 2026-09-15. Decision: **internal local candidate; not yet an externally validated v1 beta**.

In scope: source upload/processing, validated knowledge extraction and reprocessing, deterministic retrieval, six output modes, saved output revisions, multi-source context, browser screens, quota controls, private local storage, deletion and export. Deferred: public hosting/authentication, team access, embeddings, paid integrations, OCR, native mobile, and semantic contradiction guarantees.

## Reproducible internal exercise

1. Follow the root setup instructions. Start with a new private storage directory.
2. Run the synthetic demo seed. Expect two sources, six raw assets, candidate cross-source agreement, a playbook and two versions, with zero AI calls.
3. Browse the evidence and preview Workshop retrieval across both sources. One source contributes practice-break guidance; the other adds an understanding check. This demonstrates additional coverage, not independently measured improvement in output quality.
4. Open the saved playbook, edit it manually, and save another version. Reopen the original and compare.
5. Export Markdown and verify source/chunk/asset references. Download a private backup, stop the server, restore into a new folder, and check history.
6. Run `.venv/bin/python -m pytest apps/api/tests -q`.

## Real-source extraction acceptance — completed

- [x] Restore the owner's actual *Workshop Survival Guide* source and existing jobs without losing history.
- [x] Use a billing-disabled/free-tier Gemini project with `GEMINI_FREE_TIER_CONFIRMED=true`; no paid fallback exists. The application still cannot independently inspect billing configuration.
- [x] Finish the real source. Current state: **46/46 chunks interpreted**.
- [x] Audit the resulting knowledge. Latest active state: **121 assets**, **0 missing evidence**, **0 missing keywords**, confidence distribution **83 at 5 / 38 at 3**.
- [x] Review provenance defects and evidence support. Historical cross-chunk evidence leaks were reprocessed; the current cross-chunk provenance diagnostic is clean.
- [x] Review the evidence queue. **13 items remain intentionally flagged for manual review**, but inspection found them source-supported compressed or near-exact evidence rather than known defects.
- [x] Repair the known compound crowd-recovery asset. Chunk 025 now contains `Talking in circles to recover attention`; chunk 026 separately retains `Borrowing goodwill to reclaim attention`.
- [x] Validate the production extraction contract with the real provider. A strict isolated single-chunk control on chunk 007 returned **5 valid assets**, matching its historical active count, all at confidence 5.

### Extraction architecture decision

Production extraction is **one chunk per Gemini request**. Source-level orchestration may select several chunks, but each chunk has its own model context and provider attempt. Shared-context multi-chunk probes produced under-extraction and cross-chunk evidence leakage, so that path is not used for production extraction.

Gemini's asynchronous Batch API is also not used because the current Gemini Developer API free tier does not include Batch processing. The application remains within the zero-cost rule: no paid fallback, no automatic repair call, and no hidden application-level retry loop.

## Remaining real-model output acceptance

- [ ] Generate and review at least four materially different output modes with the real provider. Check structure, practical usefulness, source claims, applied asset IDs, and design-choice separation.
- [ ] Revise at least two real generated outputs and verify lineage, provenance, and preservation of the original version.
- [ ] Run one meaningful real two-source task and compare it against each single-source result. Record what improves, what remains distinct, and what remains in tension.
- [ ] Record any missed semantic conflicts or false lexical agreement/tension flags instead of treating current lexical checks as proof.

## Browser and external tester acceptance

Tester: ______  Date: ______  OS/browser: ______  Result: ______

- [ ] Create a library, add a source file and process it without a terminal.
- [ ] Interpret a chunk, understand progress, and recover a failed/stale job.
- [ ] Search within a library and select knowledge; switching libraries must clear incompatible selections.
- [ ] Preview a brief and generate a saved output. A missing key/quota must show a clear message without losing completed work.
- [ ] Read applied evidence separately from design choices; revise and compare history.
- [ ] Export the result and locate usage/data controls.
- [ ] Complete the flow using keyboard navigation with visible focus and meaningful labels.
- [ ] Check desktop and narrow mobile widths for clipped fields, unreadable text, and horizontal page overflow.
- [ ] Have someone other than the builder complete the main workflow and record feedback below.

The automated suite exercises a live localhost server, demo seeding and server restart within its test process. Full visual/mobile acceptance and external-user acceptance remain separate manual gates.

Feedback: task attempted, expected result, actual result, screenshot if useful, severity, and suggested change. Do not attach private source books or API keys to public issues.

Release gate: close the remaining real-output, browser, and external-tester checks, resolve critical defects, and explicitly change the release decision. The completed real-book extraction/audit work is no longer a release blocker.
