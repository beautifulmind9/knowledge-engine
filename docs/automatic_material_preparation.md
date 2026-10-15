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
See [Performance plan](performance_plan.md).

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
