import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {revisionPayload} from '../output-revision.js';

const parent = {
  id: 'v1', title: 'Original title', content: 'First paragraph.\n\nSecond paragraph.\n',
  design_choices: ['Keep practice short.', 'Allow reflection.'],
  version: 1, output_type: 'writing', provider: 'manual', applied_knowledge: [],
};
function formData(overrides = {}) {
  const fd = new FormData();
  const values = {
    instruction: 'Change title', manual: 'on', title: 'Revised title',
    content: parent.content.replaceAll('\n', '\r\n'),
    choices: parent.design_choices.join('\r\n'), ...overrides,
  };
  for (const [key, value] of Object.entries(values)) fd.set(key, value);
  return fd;
}

test('CRLF FormData title-only submission preserves content and design choices exactly', () => {
  const body = revisionPayload(formData(), parent);
  assert.deepEqual(body, {
    instruction: 'Change title', title: 'Revised title',
    content: parent.content, design_choices: parent.design_choices,
  });
  assert.deepEqual(['title', 'content', 'design_choices'].filter(
    key => JSON.stringify(body[key]) !== JSON.stringify(parent[key])
  ), ['title']);
});

test('untouched legacy stored line endings and choice entries round-trip exactly', () => {
  const stored = {...parent, content: 'First\r\nSecond\r', design_choices: ['First\r\nchoice', '', ' Second ']};
  const body = revisionPayload(formData({
    content: 'First\nSecond\n', choices: 'First\nchoice\n\n Second ',
  }), stored);
  assert.equal(body.content, stored.content);
  assert.deepEqual(body.design_choices, stored.design_choices);
  assert.notEqual(body.design_choices, stored.design_choices);
});

test('real whitespace and content edits survive LF normalization', () => {
  for (const edited of [parent.content + ' ', parent.content + '\n', parent.content.replace('First', 'Edited')]) {
    const body = revisionPayload(formData({content: edited.replaceAll('\n', '\r\n')}), parent);
    assert.equal(body.content, edited);
    assert.notEqual(body.content, parent.content);
    assert.deepEqual(body.design_choices, parent.design_choices);
  }
});

test('intentional choice edits survive without trailing carriage returns or whitespace trimming', () => {
  for (const [choices, expected] of [
    ['Revised rationale.\r\n Keep reflection. ', ['Revised rationale.', ' Keep reflection. ']],
    ['Keep practice short. \r\nAllow reflection.', ['Keep practice short. ', 'Allow reflection.']],
    ['', []],
  ]) {
    const body = revisionPayload(formData({choices}), parent);
    assert.deepEqual(body.design_choices, expected);
    assert.notDeepEqual(body.design_choices, parent.design_choices);
  }
});

test('AI revision sends only instruction', () => {
  assert.deepEqual(revisionPayload(formData({manual: ''}), parent), {instruction: 'Change title'});
});

test('actual output view submits title-only FormData through revisionPayload', async () => {
  const source = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  const start = source.indexOf('async function outputView(');
  const end = source.indexOf('\nasync function settingsView(', start);
  let submitRevision;
  const requests = [];
  const node = () => ({append() {}});
  const ctx = {
    revisionPayload, heading() {}, card: node, el: node, list: node,
    actions: node, button: node, detail: node, submit: node,
    main: node(), message() {}, field: () => [node(), node()],
    form: callback => {submitRevision = callback; return node();},
    api: async (url, options) => {
      if (options) {requests.push({url, body: options.body}); return {...parent, id: 'v2', version: 2};}
      if (url.endsWith('/quality')) return {validation_status: 'passed', issues: []};
      if (url.endsWith('/history')) return {items: []};
      return parent;
    },
  };
  vm.createContext(ctx);
  vm.runInContext(source.slice(start, end), ctx);
  await ctx.outputView('v1');
  await submitRevision(formData());
  assert.equal(requests[0].url, '/outputs/v1/revise');
  assert.deepEqual(requests[0].body, revisionPayload(formData(), parent));
});
