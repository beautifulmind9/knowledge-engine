# Local Workshop timing validation

This follow-up addresses a live-test failure pattern: a 40-minute Guided Practice block claiming compliance with a 20-minute teaching-format switch rule, alongside inconsistent 5/10-minute practice timings. The regression uses an original reconstruction from the reported pattern, not a recovered copy of the exact Gemini response.

## Behavior

Workshop plans receive a versioned quality report. Heading presence remains a structure hint; it is never a validity verdict. Local checks compare the requested duration with the sum of timed agenda blocks, including breaks; flag gaps, overlaps, nonpositive ranges, conflicting stated totals, and identical activity labels with inconsistent agenda/detail durations.

When retrieved canonical knowledge explicitly says to switch/change/vary/alternate teaching format every N minutes, longer non-break blocks are flagged for review with the asset ID and rule text. An unsegmented 40-minute block cannot claim verified adherence to a 20-minute switch interval. This is a review flag rather than proof of a violation: the block may contain unreported format changes, or the rule may not apply in that context. The user must show the changes or explain the scope. Design choices and usage notes do not suppress flags.

Generated results include `quality_report`, even with `save=false`. Saved/manual outputs and revisions persist their own report. `GET /outputs/{id}/quality` reevaluates an old output without an AI call or modifying its historical record. The output screen and Markdown export show the current report and concrete issues.

Outputs with problems are retained as drafts for correction, not discarded or silently regenerated. No automatic AI repair, quota increase, or retry is introduced. A corrected manual revision is checked locally and the original remains intact.

## Status meanings

| Status | Meaning |
|---|---|
| `failed` | At least one definite timing inconsistency was detected. Correct it before use. |
| `needs_review` | Timings were incomplete/ambiguous or a retrieved format-switch rule could not be verified. |
| `checks_passed` | The supported deterministic checks found no issue. Human semantic/pedagogical review is still required. |
| `not_evaluated` | This output mode has no Workshop timing validation. |

## Supported format and limits

Use an `Agenda` heading with one row per block, then a separate `Activities` heading. Prefer elapsed ranges:

```markdown
## Agenda
| Time | Activity |
| --- | --- |
| 0–20 min | Demonstration |
| 20–40 min | Pair practice |
| 40–60 min | Break |
## Activities
Pair practice (20 minutes)
```

The parser also supports bare duration rows and same-day HH:MM ranges. A brief can state `3 hours total`, `90 minutes`, or `1 hour and 30 minutes total`. Word-number durations, AM/PM schedules, overnight ranges, vague bounds, and arbitrary prose are not inferred as reliable exact timings. Unparsed agenda rows prevent a clean result. For activity cross-references, repeat the same label; nested exercises, synonyms and free-form narrative comparisons are not semantically resolved.

Numeric extraction currently covers explicit format-switch rules, not every possible numerical teaching rule. Applicability, scope, source conflicts and actual quality require review. Model instructions now ask for the supported agenda format and separately timed format changes, but deterministic checks remain necessary.

## Verification and next live test

Run `.venv/bin/python -m pytest apps/api/tests -q`. The tests include the reported 40-minute/20-minute and 5/10-minute pattern, a consistent 180-minute plan, ambiguous input, mismatched totals, gaps/overlaps, source-rule attribution, and save/revision/export integration. All tests use synthetic material and mocked provider responses; no Gemini requests are made.

After the user's quota resets, one explicitly chosen generation OR revision call can test the new behavior. Those are separate actions; testing both takes two calls. Inspect its quality report and the actual plan before deciding whether to resume book interpretation. No live call or future automatic run is scheduled by this change.

Verification result: **81 tests passed** in the full suite, with two upstream deprecation warnings. JavaScript syntax and `git diff --check` also passed. The UI change was not visually verified because this session's cloud browser cannot access the localhost app.
