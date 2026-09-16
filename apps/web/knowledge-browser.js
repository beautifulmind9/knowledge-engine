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

  const normalizedQuery = normalize(query);
  const minimumMatches = terms.length === 1
    ? 1
    : Math.max(2, Math.ceil(terms.length * 0.67));

  return items
    .map((group, index) => {
      const asset = group.canonical_asset || {};
      const title = normalize(asset.title);
      const searchable = normalize([
        asset.title,
        asset.what_it_says,
        asset.why_it_matters,
        ...(asset.keywords || []),
        asset.chapter_or_section,
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
