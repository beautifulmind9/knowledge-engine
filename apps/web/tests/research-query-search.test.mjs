import assert from 'node:assert/strict';
import {test} from 'node:test';
import {filterSearchResults} from '../knowledge-browser.js';

function unit(id, title, what_it_says = '', evidence = '') {
  return {canonical_asset: {id, title, what_it_says, evidence}};
}

const question = 'How can personality led creators develop audience trust and emotional engagement through storytelling and narrative techniques while planning practical social platform content video presentation relationships brand partnerships and long term growth?';

test('long creator research question retains substantial matching ideas, not one-word distractions', () => {
  const items = [
    unit('direct', 'Narrative storytelling builds audience trust',
      'Personality led creators use storytelling to develop emotional engagement with audiences.'),
    unit('incidental', 'Brand partnerships', 'Promotional sponsorship arrangements.'),
    unit('unrelated', 'Stock market risk', 'Liquidity and diversification.'),
  ];
  assert.deepEqual(filterSearchResults(items, question).map(g => g.canonical_asset.id), ['direct']);
});

test('research search considers source evidence in the canonical knowledge asset', () => {
  const items = [unit('supported', 'Narrative interpretation', 'Ideas for practitioners.',
    'Audience trust develops through storytelling and emotional engagement.')];
  const results = filterSearchResults(items, question);
  assert.deepEqual(results.map(g => g.canonical_asset.id), ['supported']);
});

test('short precise queries still reject one-word overlaps and blank queries stay empty', () => {
  const items = [
    unit('precise', 'One-on-one facilitation approach', 'Address individuals in a workshop.'),
    unit('generic', 'Facilitation checklist', 'Use exercises for groups.'),
  ];
  assert.deepEqual(filterSearchResults(items, 'One-on-one facilitation approach').map(g => g.canonical_asset.id), ['precise']);
  assert.deepEqual(filterSearchResults(items, '').map(g => g.canonical_asset.id), []);
});
