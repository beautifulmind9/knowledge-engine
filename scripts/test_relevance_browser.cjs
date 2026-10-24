// KE-PQ-002 synthetic acceptance: every request is intercepted; no provider IO.
const {chromium} = require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const output = process.env.KNOWLEDGE_ENGINE_SCREENSHOTS || '/tmp/ke-pq-002-relevance-browser';
const question = 'How do storytelling, curiosity, and narrative engagement help personality-led creators build lasting audience relationships?';
const libraries = [
  {id: 'marketing', name: 'Marketing'},
  {id: 'psychology', name: 'Storytelling & Audience Psychology'},
  {id: 'creators', name: 'Creator Strategy & Social Platforms'},
  {id: 'excluded', name: 'Excluded library'},
];
const selectedLibraries = libraries.slice(0, 3).map(library => library.id);
const sources = libraries.map((library, index) => ({id: `s${index + 1}`, title: `Synthetic material ${index + 1}`, library_id: library.id}));
function unit(index) {
  const source = index < 8 ? 's1' : index === 8 ? 's2' : 's3';
  return {
    canonical_asset: {id: `a${index}`, source_id: source, asset_type: 'principle',
      title: index === 8 ? 'A measured response' : `Synthetic finding ${index}`,
      what_it_says: 'A contextual finding requiring evidence review.'},
    asset_ids: [`a${index}`, ...(index === 8 ? ['a8_member'] : [])],
    source_ids: index === 8 ? ['s2', 's3'] : [source],
    support_count: index === 8 ? 2 : 1,
    relevance_score: index === 8 ? 30 : 22 - index,
    matched_terms: ['curiosity', 'narrative'],
    evidence_trail: [
      {asset_id: `a${index}`, source_id: source, chunk_id: `c${index}`, evidence: 'An excerpt with contextual limitations.'},
      ...(index === 8 ? [{asset_id: 'a8_member', source_id: 's3', chunk_id: 'c8_member', evidence: 'Storytelling curiosity narrative engagement in creator relationships.'}] : []),
    ],
  };
}
const units = Array.from({length: 15}, (_, index) => unit(index));

(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true, args: ['--no-sandbox'],
    ...(process.env.KNOWLEDGE_ENGINE_CHROME ? {executablePath: process.env.KNOWLEDGE_ENGINE_CHROME} : {})});
  const errors = [];
  try {
    for (const mobile of [false, true]) {
      const page = await browser.newPage({viewport: mobile ? {width: 390, height: 844} : {width: 1280, height: 1000}});
      page.setDefaultTimeout(10000);
      page.on('pageerror', error => errors.push(error.message));
      const requests = [];
      let failedBrowse = false;
      await page.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url()), p = url.pathname;
        if (url.origin !== 'http://ke.test') {
          errors.push(`Unexpected external request: ${url.origin}`);
          return route.abort();
        }
        if (p === '/' || p.startsWith('/static/')) {
          const file = path.join(root, 'apps/web', p === '/' ? 'index.html' : p.slice(8));
          return route.fulfill({body: fs.readFileSync(file), contentType: p.endsWith('.js') ? 'text/javascript' : p.endsWith('.css') ? 'text/css' : 'text/html'});
        }
        requests.push({path: p, method: request.method(), params: Object.fromEntries(url.searchParams),
          ...(request.method() === 'POST' ? {body: request.postDataJSON()} : {})});
        let data;
        if (p === '/libraries') data = {items: libraries};
        else if (p === '/sources') data = {items: sources};
        else if (p === '/sources/summaries') data = [];
        else if (p === '/outputs/modes') data = {items: [{id: 'knowledge_answer', label: 'Knowledge answer'}, {id: 'research_synthesis', label: 'Research synthesis'}]};
        else if (p === '/knowledge-assets/search') {
          assert.equal(url.searchParams.get('q'), question);
          const library = url.searchParams.get('library_id');
          assert.ok(selectedLibraries.includes(library), 'Find must request only a selected library');
          assert.equal(url.searchParams.has('source_id'), false);
          data = {items: units.filter(group => sources.find(source => source.id === group.canonical_asset.source_id).library_id === library)};
        } else if (/^\/sources\/s[123]\/knowledge-units$/.test(p)) {
          if (p.includes('/s3/') && !failedBrowse) {
            failedBrowse = true;
            return route.fulfill({status: 503, json: {detail: 'Synthetic inventory unavailable'}});
          }
          data = {items: units.filter(group => group.canonical_asset.source_id === p.split('/')[2]).slice(0, 2)};
        } else if (p === '/workshops/prepare' && request.method() === 'POST') {
          data = {prepared_snapshot_id: 'synthetic-server-owned-snapshot', interaction_revision: request.postDataJSON().interaction_revision,
            knowledge_unit_count: 1, knowledge_units: [units[14]], source_coverage: [{source_id: 's3', title: sources[2].title, prepared_sections: 1, total_sections: 3, relevant_idea_count: 1}],
            evidence_base: {selected_count: 3, selected_source_ids: ['s1', 's2', 's3'], ready_count: 1, preparing_count: 2, attention_count: 0, unavailable_count: 0},
            synthesis_context: {agreements: [], tensions: [], limitations: 'Synthetic context only.'}};
        } else {
          errors.push(`Unexpected request: ${request.method()} ${p}`);
          return route.abort();
        }
        return route.fulfill({json: data});
      });
      const query = new URLSearchParams({scope_mode: 'libraries'});
      for (const library of selectedLibraries) query.append('scope_library', library);
      await page.goto(`http://ke.test/#/library/explore?${query}`);
      await page.locator('#explore-request').fill(question);
      await page.getByRole('button', {name: 'Find matching ideas', exact: true}).click();
      await page.getByText('Showing 10 of 15 word-matched ideas', {exact: false}).waitFor();
      const search = page.locator('#ke-search-results');
      assert.equal(await search.locator('.card').count(), 10);
      assert.equal(await search.locator('.card h3').first().innerText(), 'A measured response');
      await search.getByText('2 supporting references · 2 materials', {exact: false}).waitFor();
      await search.getByText('Word matches: curiosity, narrative', {exact: true}).first().waitFor();
      await search.locator('.card').first().getByText('Source & evidence', {exact: true}).click();
      await search.getByText('Storytelling curiosity narrative engagement in creator relationships.', {exact: false}).waitFor();
      assert.deepEqual(requests.filter(request => request.path === '/knowledge-assets/search').map(request => request.params.library_id).sort(), [...selectedLibraries].sort());
      await page.getByRole('button', {name: 'Show more matching ideas', exact: true}).click();
      assert.equal(await search.locator('.card').count(), 15);
      await search.locator('input[name=a14]').check();
      await page.getByText('1 ideas selected for Create', {exact: true}).waitFor();
      await page.screenshot({path: path.join(output, `${mobile ? 'mobile' : 'desktop'}-find.png`), fullPage: true});
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Find must fit the viewport');

      // Query-free Browse keeps successful material inventories through a partial failure.
      await page.locator('#ke-browse > summary').click();
      await page.getByText('could not be loaded. Showing available ideas; retry the others.', {exact: false}).waitFor();
      const firstBrowseCalls = requests.filter(request => request.path.endsWith('/knowledge-units'));
      assert.deepEqual(firstBrowseCalls.map(request => request.path).sort(), ['/sources/s1/knowledge-units', '/sources/s2/knowledge-units', '/sources/s3/knowledge-units']);
      assert.ok(firstBrowseCalls.every(request => Object.keys(request.params).length === 0));
      await page.getByRole('button', {name: 'Retry unavailable materials', exact: true}).click();
      await page.getByText('across 3 of 3 materials', {exact: false}).waitFor();
      assert.equal(requests.filter(request => request.path === '/sources/s1/knowledge-units').length, 1);
      assert.equal(requests.filter(request => request.path === '/sources/s2/knowledge-units').length, 1);
      assert.equal(requests.filter(request => request.path === '/sources/s3/knowledge-units').length, 2);
      await page.locator('#ke-browse > summary').click();

      await page.getByRole('button', {name: 'Use selected ideas in Create', exact: true}).click();
      await page.locator('[name=original_request]').waitFor();
      assert.equal(await page.locator('[name=original_request]').inputValue(), question);
      assert.deepEqual(new URL(page.url()).hash.split('?')[1] && new URLSearchParams(new URL(page.url()).hash.split('?')[1]).getAll('material'), ['s1', 's2', 's3']);
      await page.getByRole('button', {name: 'Continue', exact: true}).click();
      await page.getByRole('heading', {name: '1 relevant idea found', exact: true}).waitFor();
      const prepares = requests.filter(request => request.path === '/workshops/prepare');
      assert.equal(prepares.length, 1);
      assert.deepEqual(prepares[0].body.asset_ids, ['a14']);
      assert.deepEqual(prepares[0].body.source_ids, ['s1', 's2', 's3']);
      assert.equal(requests.some(request => request.path === '/workshops/generate'), false);
      await page.goBack();
      await page.locator('#ke-search-results input[name=a14]').waitFor();
      assert.equal(await page.locator('#ke-search-results input[name=a14]').isChecked(), true);
      assert.equal(await page.locator('#ke-search-results .card').count(), 15);
      assert.equal(requests.filter(request => request.path === '/knowledge-assets/search').length, 3);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.close();
      console.log(`PASS ${mobile ? 'mobile' : 'desktop'}: exact three-library Find, backend ranking, member evidence, pagination, cached partial Browse, Create scope/selection handoff and navigation; no generation request.`);
    }
    assert.deepEqual(errors, []);
    console.log(`2 acceptance groups passed; zero runtime errors or real provider calls. Screenshots: ${output}`);
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
