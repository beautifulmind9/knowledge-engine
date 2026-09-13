# v1 beta release decision and acceptance checklist

Date: 2026-09-13. Decision: **internal local candidate; not yet an externally validated v1 beta**.

In scope: source upload/processing, validated knowledge extraction and reprocessing, deterministic retrieval, six output modes, saved output revisions, multi-source context, browser screens, quota controls, private local storage, deletion and export. Deferred: public hosting/authentication, team access, embeddings, paid integrations, OCR, native mobile, and semantic contradiction guarantees.

## Reproducible internal exercise

1. Follow the root setup instructions. Start with a new private storage directory.
2. Run the synthetic demo seed. Expect two sources, six raw assets, candidate cross-source agreement, a playbook and two versions, with zero AI calls.
3. Browse the evidence and preview Workshop retrieval across both sources. One source contributes practice-break guidance; the other adds an understanding check. This demonstrates additional coverage, not independently measured improvement in output quality.
4. Open the saved playbook, edit it manually, and save another version. Reopen the original and compare.
5. Export Markdown and verify source/chunk/asset references. Download a private backup, stop the server, restore into a new folder, and check history.
6. Run `.venv/bin/python -m pytest apps/api/tests -q`.

## Remaining real-source / model acceptance

- [ ] Restore the owner's actual Workshop Survival Guide source and existing jobs into the candidate safely.
- [ ] Confirm free-tier project settings and the intended model. No provider credentials or billing settings were verified in this pass.
- [ ] Run one chunk per action; stop at quota, resume later, and finish all remaining chunks.
- [ ] Audit a representative spread of chapters and asset types: evidence faithfulness, duplicates, confidence, false positives, missing keywords, and chapter hints. Record concrete counts and examples.
- [ ] Generate and revise at least four materially different modes with the real provider. Check format, practical usefulness, source claims and design choices. Automated provider fixtures do not close this gate.
- [ ] Run a meaningful two-source task and compare it against each single-source result. Record what improves and what remains in tension.

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

The cloud browser in this work session could not open the localhost app (`ERR_BLOCKED_BY_CLIENT`); no visual/mobile pass is claimed. The automated suite exercises a live localhost server, demo seeding and server restart within its test process.

Feedback: task attempted, expected result, actual result, screenshot if useful, severity, and suggested change. Do not attach private source books or API keys to public issues.

Release gate: close the above checks, resolve critical defects, and explicitly change the release decision. Do not mark all eight sprints complete based only on code existence or mocked AI results.
