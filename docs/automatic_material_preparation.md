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

Source readiness remains server-authoritative. New usable knowledge/actions are
shown after confirmed progress, while preparation is still running. Entering
Ask/Explore/Create leaves the preparation context and stops further dispatch.
The interface explains the tab-open requirement; there is no background promise.

Run categories are held in memory for this tab only: completed, stopped, left,
failed, uncertain, status_unavailable, daily_allowance, allowance_unavailable and
incomplete. They do not establish a provider root cause. The hosted 5/24 incident
remains unresolved. Durable client-stop diagnostics and per-attempt attribution
remain outside this slice. No source text or provider bodies are retained in
client diagnostic state.

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

Backend models, route limits, persistence, quotas, Render configuration and
provider retry/repair/fallback behavior are unchanged. Synthetic acceptance uses
`scripts/test_material_add_browser.cjs` and
`scripts/test_source_detail_browser.cjs`.
