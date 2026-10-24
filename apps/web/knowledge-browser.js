// Deterministic Knowledge-page state; no generation calls.
export const PAGE_SIZE = 10;

const SEARCH_STOPWORDS = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into',
  'is', 'it', 'of', 'on', 'one', 'or', 'that', 'the', 'this', 'to', 'with',
]);

function normalize(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function searchTerms(query) {
  return [...new Set(normalize(query).split(' ').filter(token =>
    token.length > 1 && !SEARCH_STOPWORDS.has(token)
  ))];
}

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

export function filterSearchResults(items, query) {
  const terms = searchTerms(query);
  if (!terms.length) return [];

  // Scored API results already account for every consolidated member. Preserve
  // their eligibility and order: rescoring only the canonical preview can hide
  // a match in another member or reverse the server's ranking.
  const scored = items.filter(group => Number.isFinite(group.relevance_score));
  const legacy = items.filter(group => !Number.isFinite(group.relevance_score));

  const normalizedQuery = normalize(query);
  // Short keyword searches stay precise. Full natural-language questions
  // contain background/context words that no single idea should have to repeat.
  // Require three distinct terms for longer searches rather than 67% of a
  // potentially very long question. This is lexical matching, not semantic proof.
  const minimumMatches = terms.length === 1
    ? 1
    : terms.length <= 5 ? Math.max(2, Math.ceil(terms.length * 0.67)) : 3;

  const fallback = legacy
    .map((group, index) => {
      const asset = group.canonical_asset || {};
      const title = normalize(asset.title);
      const searchable = normalize([
        asset.title,
        asset.what_it_says,
        asset.why_it_matters,
        asset.evidence,
        ...(asset.keywords || []),
        asset.chapter_or_section,
        ...(group.evidence_trail || []).map(item => item.evidence),
      ].filter(Boolean).join(' '));
      const matched = terms.filter(term => searchable.split(' ').includes(term));
      const titleMatches = terms.filter(term => title.split(' ').includes(term)).length;
      const exactTitle = normalizedQuery && title.includes(normalizedQuery);
      const exactBody = normalizedQuery && searchable.includes(normalizedQuery);

      if (!exactTitle && !exactBody && matched.length < minimumMatches) return null;

      return {
        group,
        index,
        score: (exactTitle ? 200 : exactBody ? 100 : 0) + (matched.length * 10) + (titleMatches * 3),
      };
    })
    .filter(Boolean)
    .sort((left, right) => right.score - left.score || left.index - right.index)
    .map(item => item.group);
  return [...scored, ...fallback];
}

export function ideaEvidenceSummary(group) {
  const references = Number.isInteger(group.support_count) ? group.support_count
    : (group.asset_ids || group.evidence_trail || []).length;
  const materials = new Set([
    ...(group.source_ids || []),
    ...(group.evidence_trail || []).map(item => item.source_id),
    group.canonical_asset?.source_id,
  ].filter(Boolean)).size;
  return `${references} supporting ${references === 1 ? 'reference' : 'references'} · ` +
    (materials ? `${materials} ${materials === 1 ? 'material' : 'materials'}` : 'material count unavailable');
}

export function createSearchController(load, show) {
  let revision = 0;
  return {
    invalidate() { revision++; show([], 'idle'); },
    async search(query, scope) {
      const ticket = ++revision;
      show([], 'loading', query);
      try {
        const items = filterSearchResults(await load(query, scope), query);
        if (ticket === revision) show(items, 'results', query);
      } catch (error) {
        if (ticket === revision) { show([], 'error', query); throw error; }
      }
    },
  };
}
