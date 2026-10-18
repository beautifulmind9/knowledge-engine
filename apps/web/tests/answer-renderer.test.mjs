import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderGroundedAnswer, renderGroundedInline, createAnswerEvidenceIndex, observeAnswerTableOverflow} from '../answer-renderer.js';

class Node {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this._text = ''; this.attributes = {}; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(''); }
}
const document = {createElement: tag => new Node(tag), createTextNode: text => Object.assign(new Node('#text'), {_text:String(text)})};
const descendants = node => [node, ...node.children.flatMap(descendants)];
const sourceInfo = [{id:'source_3c7cb4e7', title:'Marketing Made Simple', author:'Donald Miller'}];
const snapshot = [{canonical_asset:{id:'asset_697e6e90', title:'Relationship-first marketing'},asset_ids:['asset_697e6e90'],evidence_trail:[{source_id:'source_3c7cb4e7',chapter_or_section:'Chapter 2',evidence:'Make the message clear before asking for commitment.'}]}];

test('headings, emphasis, labels, lists, quotes, separators and tables become semantic elements', () => {
  const answer = renderGroundedAnswer(`# Core Marketing Philosophy\n\n**Principle:** Relationship comes before the offer.\n\n## Adaptation\n**Adaptation:** Use *short* language.\n\n- **Assumption:** The audience recognizes the problem.\n- **Experiment:** Test the opening.\n  - **Measurement:** Track replies.\n\n1. Define the audience.\n2. Test the message.\n\n> Make the next step clear.\n\n| Stage | Action | Signal |\n| --- | --- | --- |\n| First | Explain | Recall |\n\n---\n\nClose with ` + '`one action`' , {document});
  const nodes = descendants(answer);
  assert.ok(nodes.some(node => node.tagName === 'H2' && node.textContent === 'Core Marketing Philosophy'));
  assert.ok(nodes.some(node => node.tagName === 'H3' && node.textContent === 'Adaptation'));
  assert.ok(nodes.some(node => node.tagName === 'EM' && node.textContent === 'short'));
  assert.ok(nodes.some(node => node.className === 'answer-label answer-label-source' && node.textContent === 'Principle'));
  assert.ok(nodes.some(node => node.className === 'answer-label answer-label-inference' && node.textContent === 'Adaptation'));
  assert.ok(nodes.some(node => node.className === 'answer-label answer-label-uncertain'));
  assert.ok(nodes.some(node => node.className === 'answer-label answer-label-action'));
  assert.ok(nodes.filter(node => node.tagName === 'UL').length >= 2);
  assert.ok(nodes.some(node => node.tagName === 'OL'));
  assert.ok(nodes.some(node => node.tagName === 'BLOCKQUOTE'));
  assert.ok(nodes.some(node => node.tagName === 'TABLE' && node.children.some(child => child.tagName === 'THEAD')));
  assert.ok(nodes.some(node => node.className === 'answer-table-viewport'));
  assert.ok(nodes.some(node => node.className === 'answer-table-scroll-hint' && node.textContent.includes('Scroll sideways')));
  assert.ok(nodes.some(node => node.tagName === 'HR'));
  assert.ok(!answer.textContent.includes('##') && !answer.textContent.includes('**') && !answer.textContent.includes('| --- |'));
});

test('overflowing tables receive a visible and keyboard-accessible scroll affordance', () => {
  const viewport = new Node('div'); viewport.scrollWidth = 700; viewport.clientWidth = 300;
  viewport.setAttribute = function(name, value) { this.attributes[name] = value; };
  viewport.removeAttribute = function(name) { delete this.attributes[name]; };
  const wrapper = new Node('div'); wrapper.className = 'answer-table-scroll';
  wrapper.querySelector = selector => selector === '.answer-table-viewport' ? viewport : null;
  wrapper.classList = {toggle(name, value) { this[name] = value; }};
  const root = {querySelectorAll: selector => selector === '.answer-table-scroll' ? [wrapper] : []};
  observeAnswerTableOverflow(root);
  assert.equal(wrapper.classList['is-overflowing'], true);
  assert.equal(viewport.attributes.role, 'region');
  assert.equal(viewport.tabIndex, 0);
  assert.match(viewport.attributes['aria-label'], /scroll horizontally/i);
});

test('source and asset references resolve to human names and remain inspectable', () => {
  const answer = renderGroundedAnswer('Supported claim (Source: 3c7cb4e7). Related idea: asset_697e6e90.', {document, snapshot, sourceInfo});
  const nodes = descendants(answer);
  assert.ok(answer.textContent.includes('Marketing Made Simple · Donald Miller'));
  assert.ok(answer.textContent.includes('Make the message clear before asking for commitment.'));
  assert.ok(nodes.some(node => node.tagName === 'DETAILS' && node.children[0].textContent === 'Marketing Made Simple · Donald Miller'));
  assert.ok(!/source_3c7cb4e7|3c7cb4e7|asset_697e6e90|chunk_id|source_id/.test(answer.textContent));
});

test('evidence-aware labels render as distinct semantic markers and hex references stay private', () => {
  const answer = renderGroundedAnswer('**Source principle:** Give people a meaningful reason to join. (Source: 3c7cb4e7)\n\n**KE interpretation:** For this launch, consider early access.', {document, snapshot, sourceInfo});
  const nodes = descendants(answer);
  assert.ok(nodes.some(node => node.className === 'answer-label answer-label-source' && node.textContent === 'Source principle'));
  assert.ok(nodes.some(node => node.className === 'answer-label answer-label-inference' && node.textContent === 'KE interpretation'));
  assert.ok(answer.textContent.includes('Marketing Made Simple · Donald Miller'));
  assert.ok(!/3c7cb4e7|\*\*Source principle|\*\*KE interpretation/.test(answer.textContent));
});

test('source identity fallback omits absent author and unknown location without fabricating either', () => {
  const titleOnly = renderGroundedAnswer('Claim (Source: source_12345678).', {
    document, snapshot:[{canonical_asset:{id:'asset_1',title:'A useful idea'},asset_ids:['asset_1'],evidence_trail:[{source_id:'source_12345678',evidence:'A grounded quote.'}]}],
    sourceInfo:[{id:'source_12345678',title:'A Report'}],
  });
  assert.ok(titleOnly.textContent.includes('A Report'));
  assert.ok(titleOnly.textContent.includes('A grounded quote.'));
  assert.ok(!/undefined|null|Chapter|page/i.test(titleOnly.textContent));
  assert.ok(!/source_12345678|12345678|asset_1/.test(titleOnly.textContent));
});

test('unresolvable identifiers use neutral evidence language instead of exposing IDs', () => {
  const answer = renderGroundedAnswer('Claim (Source: deadbeef). Related asset_abcdef12 and chunk_id:chunk-private-7.', {document, snapshot:[], sourceInfo:[]});
  assert.ok(answer.textContent.includes('Source & evidence'));
  assert.ok(!/deadbeef|asset_abcdef12|chunk-private-7|chunk_id/.test(answer.textContent));
});

test('model-provided HTML is rendered as text and never creates executable elements', () => {
  const answer = renderGroundedAnswer('<img src=x onerror=alert(1)> <script>run()</script>', {document});
  const nodes = descendants(answer);
  assert.ok(!nodes.some(node => node.tagName === 'IMG' || node.tagName === 'SCRIPT'));
  assert.ok(answer.textContent.includes('<img src=x onerror=alert(1)>'));
});

test('evidence index humanizes applied-knowledge references without changing their stored IDs', () => {
  const index = createAnswerEvidenceIndex(snapshot, sourceInfo);
  assert.equal(index.assetTitle('asset_697e6e90'), 'Relationship-first marketing');
  assert.equal(index.assetTitle('asset_missing'), 'Knowledge used');
  const inline = renderGroundedInline('Use asset_697e6e90.', {document, snapshot, sourceInfo});
  assert.ok(inline.textContent.includes('Marketing Made Simple'));
  assert.ok(!inline.textContent.includes('asset_697e6e90'));
});

test('numeric titles and quantities are not mistaken for hexadecimal identifiers', () => {
  const index = createAnswerEvidenceIndex([{canonical_asset:{id:'asset_123',title:'9780143127741'},evidence_trail:[]}], []);
  assert.equal(index.assetTitle('asset_123'), '9780143127741');
  const answer = renderGroundedAnswer('The launch cap is 12345678 units.', {document, snapshot:[], sourceInfo:[]});
  assert.ok(answer.textContent.includes('12345678'));
});

test('member citations disclose only their own provenance, retaining both members in the snapshot', () => {
  const units = [{canonical_asset:{id:'asset_a', source_id:'source_a', title:'Shared idea'},
    asset_ids:['asset_a','asset_b'], source_ids:['source_a','source_b'], evidence_trail:[
      {asset_id:'asset_a',source_id:'source_a',evidence:'First evidence'},
      {asset_id:'asset_b',source_id:'source_b',evidence:'Second evidence'}]}];
  const index = createAnswerEvidenceIndex(units, [{id:'source_a',title:'First book'},{id:'source_b',title:'Second book'}]);
  assert.equal(index.asset('asset_a').label, 'First book');
  assert.deepEqual(index.asset('asset_a').evidence.map(item=>item.evidence), ['First evidence']);
  assert.equal(index.asset('asset_b').label, 'Second book');
  assert.deepEqual(index.asset('asset_b').evidence.map(item=>item.evidence), ['Second evidence']);
  assert.equal(units[0].evidence_trail.length, 2);
});

test('legacy ambiguous multi-source trails do not become member citations', () => {
  const units = [{canonical_asset:{id:'asset_a',source_id:'source_a',title:'Shared idea'},
    asset_ids:['asset_a','asset_b'], evidence_trail:[
      {source_id:'source_a',evidence:'First evidence'},{source_id:'source_b',evidence:'Second evidence'}]}];
  const index = createAnswerEvidenceIndex(units, [{id:'source_a',title:'First book'},{id:'source_b',title:'Second book'}]);
  assert.equal(index.asset('asset_a').label, 'First book');
  assert.equal(index.asset('asset_a').evidence.length, 1);
  assert.equal(index.asset('asset_b').evidence.length, 0);
});
