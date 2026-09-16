// Deterministic Knowledge-page state; no generation calls.
export const PAGE_SIZE = 10;
export function scopeQuestion(question, singleSource) {
  if (singleSource) return question;
  return question.replace('does this source teach', 'do these sources teach')
    .replace('in this source', 'in these sources')
    .replace('does this source help', 'do these sources help');
}
export function filterUnits(items, type, chapter) {
  return items.filter(group => (!type || group.canonical_asset.asset_type === type) &&
    (!chapter || [group.canonical_asset.chapter_or_section, ...(group.evidence_trail || []).map(e => e.chapter_or_section)]
      .some(value => value === chapter)));
}
export function createSearchController(load, show) {
  let revision = 0;
  return {
    invalidate() { revision++; show([], 'idle'); },
    async search(query, scope) {
      const ticket = ++revision;
      show([], 'loading', query);
      try {
        const items = await load(query, scope);
        if (ticket === revision) show(items, 'results', query);
      } catch (error) {
        if (ticket === revision) { show([], 'error', query); throw error; }
      }
    },
  };
}
