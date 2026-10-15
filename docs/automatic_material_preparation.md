# Automatic material preparation

Add material authorizes saving, deterministic reading and one foreground AI
preparation run for the successfully read files. Selection and confirmation do
not write or invoke AI. Read/upload failures retain the existing source identity.

All selected files are saved/read independently before preparation. Eligible
materials are prepared in selection order, one source at a time, with exactly
one part per interpretation request. The entire run is bounded by the shared
allowance snapshot and the remaining work. It cannot expand if allowance later
increases. The gateway still admits and counts each attempt independently.

A provider/validation failure, uncertain request, unavailable status, allowance
block, user Stop or navigation ends the foreground run. Completed knowledge and
saved sibling materials remain available. No subsequent material is dispatched
after a preparation failure or uncertainty. Continue preparing is a new explicit
action; refresh and navigation never automatically resume. Stop allows an
in-flight part to resolve without issuing another request.

A confirmed provider HTTP 503 is the one bounded automatic-recovery exception:
KE may wait for the fixed delay and make one additional **identical** provider
attempt, for at most two provider attempts total. The retry uses the same model,
payload and response contract. Each actual attempt is separately allowance-gated
and counted. HTTP 400, 429, validation failures, transport timeouts and other
failure classes are not automatically retried because their safety or outcome is
not known.

This 503 path has been exercised in the live hosted beta: the first Gemini
attempt returned 503 while Render health remained 200, the bounded second attempt
succeeded, the `/interpret?max_chunks=1` request completed 200, the source summary
refreshed 200, and preparation continued to the next part. The recovery behavior
is therefore production-observed rather than only synthetic.

Source readiness remains server-authoritative. New usable knowledge/actions are
shown after confirmed progress, while preparation is still running. Entering
Ask/Explore/Create leaves the preparation context and stops further dispatch.
The interface explains the tab-open requirement; there is no background promise.

Run categories are held in memory for this tab only: completed, stopped, left,
failed, uncertain, status_unavailable, daily_allowance, allowance_unavailable and
incomplete. They do not establish a provider root cause. Durable client-stop
diagnostics and per-attempt attribution remain outside this slice. No source text
or provider bodies are retained in client diagnostic state.

## Multi-material production observation

A real hosted multi-book run on 2026-10-15 confirmed the distinction between
**material durability** and **preparation autonomy**. Several books could be
saved/read and their completed parts persisted successfully, but preparation was
still dispatched serially in the foreground. During the run Render deployed a
new service process and shut down the prior process. The active foreground
preparation dispatcher did not survive that process lifecycle even though
already committed source state and completed knowledge did.

The user-visible result can therefore be mixed: some healthy books may reach
**Ready**, while other healthy books remain partially prepared and require an
explicit **Continue preparing** action. That partial state does not by itself mean
the file, extraction or prior knowledge failed. It can simply mean the foreground
run ended before all remaining parts were dispatched.

For product language and acceptance, distinguish at least:

- **Ready** — all currently required preparation is complete;
- **Continue preparing / Partially prepared** — saved material and completed
  knowledge are usable, but remaining parts still need dispatch;
- **Needs attention** — an actual file, extraction, provider, storage or other
  failure requires user action or investigation.

The current implementation does not provide a durable background ingestion queue.
A deployment, server restart, navigation away from the preparation context or
other foreground-run termination can stop future dispatch while preserving
completed work. Whether durable/background preparation is required for the MVP
is a usability/performance decision to be made from measured real use, not an
assumption that current partial states are data-loss defects.

## Hosted concurrency and recovery

Hosted persistence uses an optimistic revision check. Material preparation may
save progress while the user performs another independent Library action, such
as adding another material. A stale hosted revision no longer automatically
fails the user action. Persistence reloads the newest snapshot, conservatively
reapplies independent JSON changes, and retries the **state save only** within a
small fixed bound. It does not re-enter the route or service layer and therefore
cannot repeat Gemini calls, extraction, uploads, artifact publication or
allowance admission.

Overlapping edits that require choosing a winner fail closed. Independent source
creation and preparation progress, independent source changes, and concurrent
allowance increments are preserved when they can be reconciled safely. Hosted
acceptance confirmed the originally failing real workflow: one book continued
preparing while another book was added, with both records and the first book's
saved progress surviving and no stale-revision failure.

Source deletion follows a state-first safety order. Required checks run first,
the logical deletion is durably saved, and only then are source artifacts removed.
If state persistence fails, artifacts are untouched. If post-commit artifact
cleanup fails, the source remains deleted and the response may report
`artifact_cleanup_pending: true`; an orphaned private artifact is safer than a
live source record pointing to a missing file.

## Performance note

The correctness model is intentionally conservative and can be slow for large
books. Preparation is foreground, one material at a time, with one independent
Gemini request per part plus validation and progressive persistence. Provider
latency or a successful 503 retry can make a single part take substantially
longer than normal. Render free-instance cold starts and limited compute may add
more delay, while larger libraries can make summary/render paths heavier.

Performance is now an explicit beta concern. The next step is to measure upload,
extraction, chunking, provider, validation, persistence, aggregation and browser
render time separately before changing architecture or paying for infrastructure.
The real multi-book interruption above also means the benchmark must measure not
only raw speed but the cost of serial foreground dispatch and recovery after a
process/session interruption. See [Performance plan](performance_plan.md).

## Internal support

Material diagnostics remain at `#/internal/material/<source-id>`, with no link
from ordinary product navigation or the source page. Open the existing native
Advanced / Developer disclosure there to load audit, part details, history,
prompt download and structured manual import/reprocessing controls on demand.
Failed diagnostics do not block the ordinary material workspace.

This is an internal presentation path, **not separate administrator
authorization**. It retains the current shared private-beta access gate and CSRF
rules. Individual owner/admin authorization remains deferred with the accepted
identity architecture. Manage material, evidence and ordinary recovery remain
available in the product.

Backend models, route limits and quota policy remain unchanged by the preparation
UI itself. There are no automatic semantic retries, repair calls, model fallbacks
or prompt mutation. The bounded identical HTTP-503 retry described above is the
only provider retry. Synthetic acceptance uses
`scripts/test_material_add_browser.cjs` and
`scripts/test_source_detail_browser.cjs`.
