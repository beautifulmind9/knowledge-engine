// Foreground authorization only. Server jobs and source summaries own durable truth.
export function availableAIAllowance(usage) {
  if (!usage?.configured || !usage.free_tier_confirmed || usage.paused || usage.daily_limit_reached) return 0;
  const limit = Number(usage.daily_call_limit), used = Number(usage.calls_today);
  return Number.isFinite(limit) && Number.isFinite(used) ? Math.max(0, Math.floor(limit - used)) : 0;
}

export function buildQuantity(remainingParts, usage) {
  return Number.isInteger(remainingParts) && remainingParts > 0 ? Math.min(remainingParts, availableAIAllowance(usage)) : 0;
}

export function createKnowledgeBuild({sourceId, remainingParts, usage, authorizationLimit = Infinity, api, isActive = () => true, onProgress = () => {}}) {
  const authorized = Math.max(0, Math.min(buildQuantity(remainingParts, usage), authorizationLimit));
  if (!Number.isInteger(authorized)) throw Error('Build authorization must be a whole number of parts.');
  let completed = 0, started = 0, inFlight = false, stopRequested = false, status = 'idle', summary = null, summaryUnavailable = false, refreshNeeded = true, promise;
  const snapshot = () => ({authorized, completed, started, notStarted: authorized - started, inFlight, stopRequested, status, summary, summaryUnavailable});
  const notify = () => onProgress(snapshot());
  async function refreshSummary() {
    refreshNeeded = false;
    try { summary = await api(`/sources/${encodeURIComponent(sourceId)}/summary`); }
    catch { summary = null; summaryUnavailable = true; }
  }
  async function execute() {
    if (!authorized) { status = 'unavailable'; return snapshot(); }
    status = 'running'; notify();
    while (completed < authorized) {
      if (!isActive()) { status = 'left'; break; }
      if (stopRequested) { status = 'stopped'; break; }
      inFlight = true; started++; refreshNeeded = true; notify();
      let result;
      try {
        result = await api(`/sources/${encodeURIComponent(sourceId)}/interpret?max_chunks=1`, {method: 'POST'});
      } catch {
        // The server may have persisted this part. Never infer failure or retry it.
        status = isActive() ? 'uncertain' : 'left';
        inFlight = false; notify(); break;
      }
      inFlight = false;
      if (result?.processed_this_run === 1) completed++;
      if (!isActive()) status = 'left';
      else if (result?.stopped_reason) status = 'failed';
      else if (result?.processed_this_run !== 1) status = 'uncertain';
      else if (stopRequested) status = 'stopped';
      else if (completed === authorized) status = 'completed';
      notify();
      if (result?.processed_this_run === 1 && !result.stopped_reason && isActive()) {
        await refreshSummary();
        if (!isActive()) status = 'left';
        else if (summaryUnavailable) status = 'status_unavailable';
        notify();
      }
      if (status !== 'running') break;
    }
    if (isActive() && refreshNeeded) await refreshSummary();
    if (!isActive()) status = 'left';
    notify(); return snapshot();
  }
  return {
    snapshot,
    // Repeated activation returns the same run; no restart or automatic resumption.
    run: () => promise ??= Promise.resolve().then(execute),
    stop() {
      if (!stopRequested) {
        stopRequested = true;
        if (!inFlight && ['idle', 'running'].includes(status)) status = 'stopped';
        notify();
      }
    },
  };
}
