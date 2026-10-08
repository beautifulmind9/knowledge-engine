import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {csrfToken, csrfOptions, api, apiFetch, CSRF_COOKIE} from '../api.js';

const origin = 'https://private.example';
const cookie = `other=x; ${CSRF_COOKIE}=session-bound-token`;

test('CSRF cookie decoding handles missing and malformed values', () => {
  assert.equal(csrfToken(cookie), 'session-bound-token');
  assert.equal(csrfToken(''), '');
  assert.equal(csrfToken(`${CSRF_COOKIE}=%broken`), '');
  assert.equal(csrfToken(`${CSRF_COOKIE}=a%2Bb`), 'a+b');
});

for (const method of ['POST', 'PUT', 'PATCH', 'DELETE', 'post']) {
  test(`${method} receives CSRF automatically without changing body or headers`, () => {
    const body = new FormData(); body.append('file', 'fixture');
    const original = {method, body, headers: {'X-Existing': 'kept', 'X-CSRF-Token': 'stale'}};
    const result = csrfOptions('/sources/id/upload', original, {cookie, origin});
    assert.equal(result.headers.get('X-CSRF-Token'), 'session-bound-token');
    assert.equal(result.headers.get('X-Existing'), 'kept');
    assert.equal(result.headers.has('Content-Type'), false);
    assert.equal(result.body, body);
    assert.equal(original.headers['X-CSRF-Token'], 'stale');
  });
}

for (const method of ['GET', 'HEAD', 'OPTIONS']) {
  test(`${method} does not add CSRF`, () => {
    const result = csrfOptions('/libraries', {method}, {cookie, origin});
    assert.equal(result.headers, undefined);
  });
}

test('local mode without a CSRF cookie keeps requests usable', () => {
  const result = csrfOptions('/libraries', {method:'POST'}, {cookie:'', origin});
  assert.equal(result.headers.has('X-CSRF-Token'), false);
});

test('CSRF is never added to external or unknown-origin URLs', () => {
  for (const target of ['https://elsewhere.example/api', '//elsewhere.example/api']) {
    assert.equal(csrfOptions(target, {method:'POST'}, {cookie, origin}).headers, undefined);
  }
  assert.equal(csrfOptions('/libraries', {method:'POST'}, {cookie, origin:undefined}).headers, undefined);
});

test('Request method and headers are supported', () => {
  const request = new Request(origin + '/libraries', {method:'DELETE', headers:{'X-Existing':'kept'}});
  const result = csrfOptions(request, {}, {cookie, origin});
  assert.equal(result.headers.get('X-CSRF-Token'), 'session-bound-token');
  assert.equal(result.headers.get('X-Existing'), 'kept');
});

test('actual JSON and multipart API calls go through the centralized transport', async () => {
  const originalFetch = globalThis.fetch, originalDocument = globalThis.document, originalLocation = globalThis.location;
  const calls = [];
  globalThis.document = {cookie};
  globalThis.location = {origin};
  globalThis.fetch = async (path, init) => {calls.push([path, init]); return {ok:true, status:200, json:async()=>({ok:true})};};
  try {
    assert.deepEqual(await api('/libraries', {method:'POST', body:{name:'Fixture'}}), {ok:true});
    assert.equal(calls[0][1].headers.get('X-CSRF-Token'), 'session-bound-token');
    assert.equal(calls[0][1].headers.get('Content-Type'), 'application/json');
    assert.equal(calls[0][1].body, '{"name":"Fixture"}');
    const upload = new FormData(); upload.append('file', 'bytes');
    await api('/sources/id/upload', {method:'POST', body:upload});
    assert.equal(calls[1][1].body, upload);
    assert.equal(calls[1][1].headers.has('Content-Type'), false);
    await api('/libraries');
    assert.equal(calls[2][1].headers, undefined);
  } finally {globalThis.fetch=originalFetch;globalThis.document=originalDocument;globalThis.location=originalLocation;}
});

test('unauthenticated fetch sends the browser to the login page', async () => {
  const originalFetch=globalThis.fetch, originalLocation=globalThis.location;
  const locations=[];
  globalThis.location={origin, assign:target=>locations.push(target)};
  globalThis.fetch=async()=>({status:401});
  try {await apiFetch('/libraries');assert.deepEqual(locations,['/login']);}
  finally {globalThis.fetch=originalFetch;globalThis.location=originalLocation;}
});

test('centralized transport preserves both Workshop enrichment wrappers', async () => {
  const calls=[];
  const fields = {'#ke-output-format-host select[name="output_format"]':'Email', '[name="creative_intent"]':'Personal', '[name="creator_context"]':'Fixture', '[name="preserve"]':'Warmth', '[name="avoid"]':'Jargon'};
  const context={URL,Headers,FormData,console,location:{origin},document:{cookie, querySelector:selector=>selector in fields?{value:fields[selector]}:null},
    fetch:async(path,options)=>{calls.push([path,options]);return {ok:true,status:200,json:async()=>({ok:true})};}};
  context.window=context;
  vm.createContext(context);
  const apiSource=readFileSync(new URL('../api.js',import.meta.url),'utf8').replaceAll('export ', '');
  vm.runInContext(apiSource,context);
  const enhancements=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
  vm.runInContext(enhancements.slice(enhancements.indexOf('const nativeFetch'),enhancements.indexOf('function makeElement')),context);
  const creator=readFileSync(new URL('../creator-direction.js',import.meta.url),'utf8').replaceAll('export ', '');
  vm.runInContext(creator,context);
  await context.api('/workshops/generate',{method:'POST',body:{situation:'Fixture',goal:'Fixture'}});
  const body=JSON.parse(calls[0][1].body);
  assert.equal(body.output_format,'Email');
  assert.equal(body.creative_intent,'Personal');
  assert.deepEqual(body.preserve,['Warmth']);
  assert.equal(calls[0][1].headers.get('X-CSRF-Token'),'session-bound-token');
});

test('every application fetch entrypoint uses the shared CSRF transport', () => {
  const app=readFileSync(new URL('../app.js',import.meta.url),'utf8');
  const enhancements=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
  assert.match(app,/import \{api, apiFetch, csrfToken\} from '\.\/api.js'/);
  assert.match(enhancements,/import \{apiFetch\} from '\.\/api.js'/);
  assert.doesNotMatch(app,/\bfetch\(/);
  assert.doesNotMatch(enhancements,/await fetch\(/);
  assert.match(app,/apiFetch\('\/logout', \{method: 'POST'\}\)/);
});
