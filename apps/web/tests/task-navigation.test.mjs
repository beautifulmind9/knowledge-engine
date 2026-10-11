import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createNavigation, parseRoute, routeHash} from '../navigation.js';
import {PAGE_SIZE, filterUnits, createSearchController} from '../knowledge-browser.js';
import {revisionPayload} from '../output-revision.js';
import * as interaction from '../interaction-draft.js';
const app=readFileSync(new URL('../app.js',import.meta.url),'utf8');
class Node {
 constructor(tag){this.tag=tag;this.children=[];this._value='';this.attributes={};this.listeners={};}
 append(...nodes){for(const n of nodes){n.remove();n.parent=this;this.children.push(n);}}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null;}
 replaceChildren(...nodes){for(const n of this.children)n.parent=null;this.children=[];this.append(...nodes);}
 insertBefore(node,before){node.remove();node.parent=this;this.children.splice(this.children.indexOf(before),0,node);}
 after(node){node.remove();node.parent=this.parent;this.parent.children.splice(this.parent.children.indexOf(this)+1,0,node);}
 closest(selector){return matches(this,selector)?this:this.parent?.closest(selector);}
 setAttribute(name,value){this.attributes[name]=value;} removeAttribute(name){delete this.attributes[name];} focus(){this.focused=true;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 querySelectorAll(selector){const parts=selector.split(/\s+(?![^\[]*\])/);let roots=[this];for(const part of parts)roots=roots.flatMap(root=>all(root).slice(1).filter(n=>matches(n,part)));return roots;}
 get isConnected(){return this.tag==='body'||!!this.parent?.isConnected;}
 get elements(){return {namedItem:name=>all(this).find(n=>n.name===name)};}
 get value(){return this.tag==='select'?this.selectedOptions[0]?.value||'':this._value;}
 set value(value){this._value=value;if(this.tag==='select')for(const o of this.children)o.selected=o.value===value;}
 get options(){return this.children;}
 get selectedOptions(){const selected=this.children.filter(n=>n.selected);return !this.multiple&&!selected.length&&this.children.length?[this.children[0]]:selected;}
 addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
 dispatchEvent(event){this['on'+event.type]?.(event);for(const fn of this.listeners[event.type]||[])fn(event);if(event.bubbles)this.parent?.dispatchEvent(event);return true;}
 reportValidity(){return true;}
}
function matches(n,selector){const attr=selector.match(/\[([^=]+)=['"]?([^'"\]]+)['"]?\]/);if(attr&&String(n[attr[1]])!==attr[2])return false;selector=selector.replace(/\[.*?\]/,'');const id=selector.match(/#([\w-]+)/),cls=selector.match(/\.([\w-]+)/),tag=selector.match(/^[\w-]+/);return (!id||n.id===id[1])&&(!cls||n.className?.split(' ').includes(cls[1]))&&(!tag||n.tag===tag[0]);}
const all=n=>[n,...n.children.flatMap(all)];
function browserStub(hash=''){
 const location={hash},entries=[hash],listeners={};let index=0;
 const browser={location,addEventListener(type,fn){(listeners[type]??=[]).push(fn);},async dispatch(type){await Promise.all((listeners[type]||[]).map(fn=>fn()));},history:{
  pushState(_state,_title,next){entries.splice(++index);entries.push(next);location.hash=next;},
  replaceState(_state,_title,next){entries[index]=next;location.hash=next;},
  async back(){if(index){location.hash=entries[--index];await Promise.all((listeners.popstate||[]).map(fn=>fn()));}},
  async forward(){if(index<entries.length-1){location.hash=entries[++index];await Promise.all((listeners.popstate||[]).map(fn=>fn()));}},
 }};return browser;
}
async function fixture(hash='',authenticated=false){
 const main=new Node('main'),feedback=new Node('div'),body=new Node('body'),requests=[],browser=browserStub(hash);main.id='main';feedback.id='feedback';body.append(main,feedback);const nav=['home','library','workshop','outputs','settings'].map(view=>{const n=new Node(view==='home'?'a':'button');n.dataset={view};return n;});
 const source={id:'s1',title:'A book',author:'A writer',library_id:'l1',file_path:'file',processing_status:'uploaded'};
 const audit={interpretation:{completed_chunks:1,total_chunks:3},overlap_rate:0,superseded_assets:[],old_schema_assets:[],missing_evidence:[],missing_keywords:[],evidence_needing_review:[],asset_types:{},confidence_distribution:{},jobs:[{id:'j1',chunk_id:'c1',status:'failed'}]};
 const document={body,querySelector:s=>s==='main'?main:s==='#feedback'?feedback:body.querySelector(s),querySelectorAll:s=>s==='[data-view]'?nav:s==='nav button'?nav.filter(n=>n.tag==='button'):body.querySelectorAll(s),createElement:tag=>new Node(tag),dispatchEvent(){}};
 const ctx={...interaction,console,URLSearchParams,Event,window:browser,createNavigation,PAGE_SIZE,filterUnits,createSearchController,revisionPayload,Option:function(text,value){const n=new Node('option');n.textContent=text;n.value=value;return n;},FormData:class {constructor(form){this.values=form?all(form).filter(n=>n.name&&!n.disabled&&!(n.type==='checkbox'&&!n.checked)).flatMap(n=>n.tag==='select'?n.selectedOptions.filter(o=>!o.disabled).map(o=>[n.name,o.value]):[[n.name,n.value]]):[];}get(name){return this.values.find(pair=>pair[0]===name)?.[1]||'';}[Symbol.iterator](){return this.values[Symbol.iterator]();}},Set,Map,Date,document,api:async(path,options)=>{requests.push({path,options});if(options){if(path==='/workshops/prepare')return {prepared_snapshot_id:'server-snapshot-reference-12345',interaction_revision:options.body.interaction_revision,source_coverage:[{title:'A book',prepared_sections:1,total_sections:3,relevant_idea_count:1}],knowledge_unit_count:1,knowledge_units:[{canonical_asset:{title:'An idea'},source_ids:['s1']}],synthesis_context:{agreements:[],tensions:[],limitations:''}};if(path==='/workshops/generate')return {saved_output:{id:'new-work'}};if(path.endsWith('/process'))source.chunks_path='chunks';return {processed_this_run:1};}if(path==='/outputs/modes')return {items:[{id:'writing',label:'Writing',formats:['Email','Essay']},{id:'knowledge_answer',label:'Knowledge answer'}]};if(path==='/libraries')return {items:[{id:'l1',name:'Reading'}]};if(path.startsWith('/sources?')||path==='/sources')return {items:[source]};if(path.endsWith('/audit'))return audit;if(path.endsWith('/chunks'))return {items:[{id:'c1',chunk_index:1,word_count:100}]};if(path.endsWith('/knowledge-units'))return {items:[{canonical_asset:{title:'An idea',what_it_says:'Useful insight'}}]};if(path==='/sources/s1')return source;if(path.endsWith('/quality'))return {validation_status:'passed',issues:[]};if(path.endsWith('/history'))return {items:[]};if(/^\/outputs\/[^/]+$/.test(path))return {id:path.split('/').at(-1),title:'My essay',content:'The artifact',version:1,output_type:'writing',provider:'manual',applied_knowledge:[],design_choices:[]};if(path==='/usage')return {configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:10};if(path==='/data/integrity')return {ok:true,issues:[]};if(path==='/outputs')return {items:[{id:'o1',title:'My essay',root_output_id:'o1',output_type:'writing',version:1}],count:1};throw Error(path);},csrfToken:()=>authenticated?'fixture-token':null};
 vm.createContext(ctx);vm.runInContext(readFileSync(new URL('../create-draft.js',import.meta.url),'utf8').replaceAll('export ',''),ctx);vm.runInContext(app.replace(/^import .*;\n/gm,''),ctx);await new Promise(resolve=>setImmediate(resolve));
 return {ctx,main,document,browser,nav,requests,source,audit,nodes:()=>all(main),click:async text=>{const n=all(main).find(n=>n.tag==='button'&&n.textContent===text);assert.ok(n,text);if(n.onclick)await n.onclick();else await n.closest('form').onsubmit({preventDefault(){}});}};
}
test('Home actions route to Library, Create and My work; shell has task navigation',async()=>{
 const f=await fixture();
 for(const [action,target] of [['Add to my library','library'],['Create something','workshop'],['Continue my work','outputs']]){await f.ctx.navigate('home');await f.click(action);assert.equal(parseRoute(f.browser.location.hash).view,target);}
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 assert.match(html,/data-view="home"/);assert.match(html,/>Library<.*>Create<.*>My work</s);assert.match(html,/>Settings</);assert.doesNotMatch(html,/Local personal beta|<aside|>Knowledge<|>Workshop<|Saved outputs|Data &amp; usage|>Source</);
});
test('Library opens material; preparation and recovery keep existing endpoints and partial state',async()=>{
 const f=await fixture();await f.ctx.libraryView();await f.click('Open material');await f.click('Prepare material');
 assert.ok(f.requests.some(r=>r.path==='/sources/s1/process'&&r.options.method==='POST'));
 assert.equal(f.main.querySelector('.kicker').textContent,'Preparing');
 assert.ok(f.nodes().some(n=>n.textContent==='1 of 3 sections prepared'));
 assert.ok(f.nodes().some(n=>n.textContent==='An idea: Useful insight'));
 const advanced=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Advanced details');assert.ok(advanced);assert.ok(!advanced.open);
 assert.ok(all(advanced).some(n=>n.textContent==='Manual extraction or intentional reprocessing'));
 await f.click('Continue preparing');assert.ok(f.requests.some(r=>r.path==='/sources/s1/interpret?max_chunks=1'&&r.options.method==='POST'));
 await f.click('Recover job');assert.ok(f.requests.some(r=>r.path==='/knowledge-extractions/j1/recover'&&r.options.method==='POST'));
 f.audit.interpretation.completed_chunks=3;await f.ctx.sourceView('s1');assert.equal(f.main.querySelector('.kicker').textContent,'Ready to use');assert.ok(!f.nodes().some(n=>n.textContent==='Continue preparing'));
});
test('My work opens stored work and Settings retains usage and backup controls',async()=>{
 const f=await fixture();await f.ctx.savedView();await f.click('Open work');assert.equal(f.browser.location.hash,'#/my-work/o1');
 await f.ctx.settingsView();assert.ok(f.nodes().some(n=>n.textContent==='AI usage'));assert.ok(f.nodes().some(n=>n.href==='/data/export'));assert.ok(f.requests.some(r=>r.path==='/data/integrity'));
});

test('Create previews retrieved ideas and sends explicit selections; picker preserves the brief',async()=>{
 const f=await fixture();vm.runInContext("state.selected.add('idea1');state.source='s1';state.library='l1'",f.ctx);
 await f.ctx.workshopView();const situation=f.nodes().find(n=>n.name==='original_request');situation.value='Write a thoughtful essay';
 await f.click('Continue');const preview=f.requests.find(r=>r.path==='/workshops/prepare');assert.deepEqual([...preview.options.body.asset_ids],['idea1']);assert.deepEqual([...preview.options.body.source_ids],['s1']);assert.equal(preview.options.body.situation,situation.value);
 assert.ok(f.nodes().some(n=>n.textContent==='1 relevant idea found'));
 await f.click('Choose ideas myself');assert.equal(parseRoute(f.browser.location.hash).view,'knowledge');await f.click('Use selected ideas →');assert.equal(f.nodes().find(n=>n.name==='original_request').value,'Write a thoughtful essay');
 await f.click('Create essay');await new Promise(resolve=>setImmediate(resolve));assert.equal(f.browser.location.hash,'#/my-work/new-work?library=l1');assert.ok(f.requests.some(r=>r.path==='/workshops/generate'));
});
test('Stored work shows artifact first, expandable evidence, history, compare and revision',async()=>{
 const f=await fixture();const requests=[];
 f.ctx.api=async(path,options)=>{requests.push({path,options});if(path.endsWith('/quality'))return {validation_status:'passed',issues:[]};if(path.endsWith('/history'))return {items:[{id:'o1',version:1},{id:'o2',version:2}]};if(path.includes('/compare/'))return {changed_fields:['content'],content_diff:'An edit'};if(path.endsWith('/revise'))return {id:'o2',version:2};return {id:'o1',title:'My essay',content:'The artifact',output_type:'writing',version:1,provider:'manual',applied_knowledge:[],design_choices:[]};};
 f.ctx.revisionPayload=()=>({instruction:'Revise'});await f.ctx.outputView('o1');
 const article=f.nodes().find(n=>n.tag==='article');assert.equal(article.textContent,'The artifact');const evidence=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Ideas and evidence used');assert.ok(f.main.children.indexOf(article)<f.main.children.indexOf(evidence));assert.ok(!evidence.open);
 assert.ok(f.nodes().some(n=>n.href==='/outputs/o1/export'));await f.click('Compare v1 → v2');assert.ok(requests.some(r=>r.path==='/outputs/o1/compare/o2'));await f.click('Open version 2');assert.ok(requests.some(r=>r.path==='/outputs/o2'));
 const form=f.nodes().find(n=>n.tag==='form');await form.onsubmit({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));assert.ok(requests.some(r=>r.path==='/outputs/o2/revise'&&r.options.method==='POST'));
});

const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('actual navigation restores every primary view on startup/refresh and falls back to Home',async()=>{
 for(const [hash,title] of [['','What would you like to do?'],['#/home','What would you like to do?'],['#/library','Your library'],['#/create','What are you working on?'],['#/my-work','Work worth coming back to.'],['#/settings','Your data, in your hands.'],['#/missing','What would you like to do?']]){
  const f=await fixture(hash);assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,title);assert.equal(f.main.attributes['aria-busy'],undefined);
  const refreshed=await fixture(f.browser.location.hash);assert.equal(refreshed.nodes().find(n=>n.tag==='h1').textContent,title);
 }
});
test('Home Add action expands the existing form; actual back/forward restores views and details',async()=>{
 const f=await fixture();await f.click('Add to my library');
 const add=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Add material');assert.equal(add.open,true);assert.equal(parseRoute(f.browser.location.hash).add,true);
 await f.click('Open material');assert.equal(f.browser.location.hash,'#/library/material/s1');assert.equal(f.nav.find(n=>n.dataset.view==='library').attributes['aria-current'],'page');
 const refreshed=await fixture(f.browser.location.hash);assert.equal(refreshed.nodes().find(n=>n.tag==='h1').textContent,'A book');
 await f.browser.history.back();assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'Your library');assert.equal(f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Add material').open,true);
 await f.browser.history.back();assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'What would you like to do?');
 await f.browser.history.forward();await f.browser.history.forward();assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'A book');
 for(const view of ['workshop','outputs','settings'])await f.ctx.navigate(view);
 await f.browser.history.back();assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'Work worth coming back to.');await f.browser.history.back();assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'What are you working on?');await f.browser.history.forward();await f.browser.history.forward();assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'Your data, in your hands.');
});
test('delayed view loads cannot append controls or headings after navigation to Home',async()=>{
 for(const [view,path] of [['library','/libraries'],['library','/sources'],['material','/sources/s1'],['material','/sources/s1/audit'],['material','/sources/s1/knowledge-units'],['workshop','/outputs/modes'],['outputs','/outputs'],['work','/outputs/o1'],['work','/outputs/o1/quality'],['work','/outputs/o1/history'],['settings','/usage']]){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='chunks';let release;
  f.ctx.api=(url,options)=>url===path?new Promise(resolve=>{release=async()=>resolve(await original(url,options));}):original(url,options);
  const pending=f.ctx.navigate(view,{id:view==='material'?'s1':'o1'});await settle();assert.ok(release,`${view} ${path}`);
  await f.ctx.navigate('home');await release();await pending;
  assert.deepEqual(f.main.children.map(n=>n.tag),['div','h1','p','div'],`${view} ${path}`);assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'What would you like to do?');assert.equal(f.main.attributes['aria-busy'],undefined);
 }
});
test('Create navigation round-trip restores core, format and creator fields; clear selection preserves edits',async()=>{
 const f=await fixture();await f.ctx.navigate('workshop');f.document.querySelector('[name=original_request]').value='An intimate essay';await f.click('Continue');
 const values={situation:'An intimate essay',goal:'Explain my experience',audience:'Friends',constraints:'Keep the pauses',tone_or_style:'Personal',output_format:'Email',creative_intent:'Imperfect',creator_context:'A personal memory',preserve:'My voice\nLong pause',avoid:'Jargon'};
 for(const [name,value] of Object.entries(values))f.document.querySelector(`[name="${name}"]`).value=value;
 vm.runInContext("state.selected.add('a1')",f.ctx);await f.click('Clear idea selection');assert.equal(f.document.querySelector('[name="situation"]').value,values.situation);
 await f.click('Choose ideas myself');await f.click('Use selected ideas →');
 for(const [name,value] of Object.entries(values))assert.equal(f.document.querySelector(`[name="${name}"]`).value,value,name);
 assert.ok(!f.browser.location.hash.includes('intimate'));await f.ctx.navigate('settings');await f.browser.history.back();assert.equal(f.document.querySelector('[name="creative_intent"]').value,values.creative_intent);
});
test('chosen material subset bounds picker search/browse and stays consistent on return and refresh',async()=>{
 const f=await fixture(),original=f.ctx.api;
 const sources=[f.source,{...f.source,id:'s2',title:'Second book'},{...f.source,id:'s3',title:'Excluded book'},{...f.source,id:'s4',library_id:'l2',title:'Other library'}];
 f.ctx.api=(path,options)=>{if(!options&&(path==='/sources'||path.startsWith('/sources?')))return Promise.resolve({items:sources});if(path.startsWith('/knowledge-assets/search?')){f.requests.push({path});return Promise.resolve({items:[]});}return original(path,options);};
 await f.ctx.navigate('workshop',{library:'l1',materials:['s1','s2']});f.document.querySelector('[name="original_request"]').value='Write an essay using chosen books';await f.click('Continue');
 await f.click('Choose ideas myself');const scope=f.document.querySelector('#ke-source-scope');assert.deepEqual(scope.options.map(o=>o.value),['','s1','s2']);assert.equal(scope.value,'');
 f.document.querySelector('[name="q"]').value='useful ideas';await f.click('Find ideas');const searches=f.requests.filter(r=>r.path.startsWith('/knowledge-assets/search?'));assert.deepEqual(searches.map(r=>new URLSearchParams(r.path.split('?')[1]).get('source_id')),['s1','s2']);
 const browse=f.document.querySelector('#ke-browse');browse.open=true;await browse.ontoggle();assert.ok(!f.requests.some(r=>r.path==='/sources/s3/knowledge-units'));
 scope.value='s2';scope.onchange();vm.runInContext("state.selected.add('idea-from-s2')",f.ctx);await f.click('Use selected ideas →');
 const materials=f.nodes().filter(n=>n.type==='checkbox'&&n.name?.startsWith('material_'));assert.deepEqual(materials.filter(n=>n.checked).map(n=>n.value),['s1','s2']);assert.deepEqual([...f.requests.filter(r=>r.path==='/workshops/prepare').at(-1).options.body.asset_ids],['idea-from-s2']);
 materials.forEach(o=>o.checked=o.value==='s1');await materials[0].onchange();const last=f.requests.filter(r=>r.path==='/workshops/prepare').at(-1);assert.deepEqual([...last.options.body.source_ids],['s1']);assert.deepEqual([...last.options.body.asset_ids],[]);
 const refreshed=await fixture(f.browser.location.hash);refreshed.document.querySelector('[name=original_request]').value='Write an essay';await refreshed.click('Continue');assert.deepEqual(refreshed.nodes().filter(n=>n.type==='checkbox'&&n.name?.startsWith('material_')&&n.checked).map(n=>n.value),['s1']);assert.equal(refreshed.document.querySelector('[name="Library scope"]').value,'l1');
});
test('route IDs round-trip safely and malformed routes fall back to Home',()=>{
 const route={view:'material',id:'book / #?',library:'reading & notes'};assert.equal(parseRoute(routeHash(route)).id,route.id);assert.equal(parseRoute(routeHash(route)).library,route.library);assert.equal(parseRoute('#/library/material/%ZZ').view,'home');
});
test('authenticated Settings startup shows Sign out and removes it from other primary views',async()=>{
 const f=await fixture('#/settings',true);assert.equal(f.document.querySelector('#beta-logout').hidden,false);assert.ok(f.nodes().some(n=>n.id==='beta-logout'));
 await f.ctx.navigate('home');assert.equal(f.document.querySelector('#beta-logout').hidden,true);assert.ok(!f.nodes().some(n=>n.id==='beta-logout'));
 await f.browser.history.back();assert.ok(f.nodes().some(n=>n.id==='beta-logout'&&!n.hidden));
});
test('scope changes invalidate pending Create preview results without erasing the brief',async()=>{
 const f=await fixture();await f.ctx.navigate('workshop');f.document.querySelector('[name="original_request"]').value='Write an essay';const original=f.ctx.api;let release;
 f.ctx.api=(path,options)=>path==='/workshops/prepare'?new Promise(resolve=>{release=async()=>resolve(await original(path,options));}):original(path,options);
 const pending=f.click('Continue');f.document.querySelector('[name=constraints]').value='Under 100 words';f.document.querySelector('[name=constraints]').oninput();await release();await pending;
 assert.ok(!f.nodes().some(n=>n.textContent==='1 relevant idea found'));assert.equal(f.document.querySelector('[name="original_request"]').value,'Write an essay');
});
test('a completed preparation request cannot reopen material or report success after navigating away',async()=>{
 const f=await fixture();await f.ctx.navigate('material',{id:'s1'});const original=f.ctx.api;let release;
 f.ctx.api=(path,options)=>path==='/sources/s1/process'?new Promise(resolve=>{release=async()=>resolve(await original(path,options));}):original(path,options);
 const pending=f.click('Prepare material');await f.ctx.navigate('home');await release();await pending;
 assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'What would you like to do?');assert.equal(f.document.querySelector('#feedback').textContent,'');
});
test('hash changes restore views once, preserve skip-to-content, and restore saved artifact details',async()=>{
 const f=await fixture();f.browser.location.hash='#/my-work/o1';await f.browser.dispatch('popstate');const count=f.requests.length;await f.browser.dispatch('hashchange');assert.equal(f.requests.length,count);assert.equal(f.nodes().find(n=>n.tag==='article').textContent,'The artifact');assert.equal(f.nav.find(n=>n.dataset.view==='outputs').attributes['aria-current'],'page');
 const refreshed=await fixture(f.browser.location.hash);assert.equal(refreshed.nodes().find(n=>n.tag==='article').textContent,'The artifact');
 f.browser.location.hash='#main';await f.browser.dispatch('hashchange');assert.equal(f.nodes().find(n=>n.tag==='article').textContent,'The artifact');
 f.browser.location.hash='#/settings';await f.browser.dispatch('hashchange');assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'Your data, in your hands.');
});

test('Create starts with one natural request, not a schema wall; local editing and navigation make zero AI requests',async()=>{
 const f=await fixture('#/create');assert.ok(f.document.querySelector('[name=original_request]'));
 for(const name of ['situation','goal','audience','constraints','tone_or_style','creative_intent','preserve','avoid'])assert.equal(f.document.querySelector(`[name=${name}]`),null);
 const request=f.document.querySelector('[name=original_request]');request.value='Write an essay. Do not use jargon. Preserve my voice.';request.oninput();
 await f.ctx.navigate('home');await f.browser.history.back();assert.equal(f.document.querySelector('[name=original_request]').value,request.value);
 assert.equal(f.requests.filter(r=>r.options).length,0);
 await f.click('Continue');assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
 const preserve=f.document.querySelector('[name=preserve]');preserve.value='Keep my ending';preserve.oninput();await f.ctx.navigate('settings');await f.browser.history.back();assert.equal(f.document.querySelector('[name=preserve]').value,'Keep my ending');assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
});

test('task/constraint/request edits during preparation cannot restore stale evidence or errors',async()=>{
 for(const edit of ['task','constraints','original_request'])for(const failure of [false,true]){
  const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay';
  const original=f.ctx.api;let release;
  f.ctx.api=(path,options)=>path==='/workshops/prepare'?new Promise((resolve,reject)=>{release=()=>failure?reject(Error('Old failure')):resolve({knowledge_unit_count:1,knowledge_units:[],synthesis_context:{agreements:[],tensions:[]}});}):original(path,options);
  const pending=f.click('Continue');const input=f.document.querySelector(`[name=${edit}]`);input.value='A newer direction';input.oninput();release();await pending;
  assert.ok(!f.nodes().some(n=>n.textContent==='1 relevant idea found'));assert.ok(!f.document.querySelector('#feedback').textContent.includes('Old failure'));assert.equal(input.value,'A newer direction');
 }
});

test('late generation cannot redirect after editing or navigation; each action sends one generation request',async()=>{
 for(const change of ['edit','navigate'])for(const failure of [false,true]){
  const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
  const original=f.ctx.api;let release,calls=0;
  f.ctx.api=(path,options)=>path==='/workshops/generate'?new Promise((resolve,reject)=>{calls++;release=()=>failure?reject(Error('Old generation failure')):resolve({saved_output:{id:'old-result'}});}):original(path,options);
  const pending=f.click('Create essay');
  if(change==='edit'){const input=f.document.querySelector('[name=original_request]');input.value='Write something newer';input.oninput();}else await f.ctx.navigate('home');
  release();await pending;assert.equal(calls,1);assert.ok(!f.browser.location.hash.includes('old-result'));assert.ok(!f.document.querySelector('#feedback').textContent.includes('Old generation failure'));
 }
});

test('preparation and generation failures retain corrections and have no automatic retry/repair/fallback',async()=>{
 for(const endpoint of ['/workshops/prepare','/workshops/generate']){
  const f=await fixture('#/create');const input=f.document.querySelector('[name=original_request]');input.value='Write an essay. Preserve my ending.';
  if(endpoint.endsWith('generate'))await f.click('Continue');
  const original=f.ctx.api,attempts=[];f.ctx.api=(path,options)=>{if(options){attempts.push(path);if(path===endpoint)throw Error('Synthetic provider or preparation failure');}return original(path,options);};
  if(endpoint.endsWith('prepare'))await f.click('Continue');else await f.click('Create essay');
  await settle();assert.deepEqual(attempts,[endpoint]);assert.equal(input.value,'Write an essay. Preserve my ending.');
  assert.ok(f.document.querySelector('[name=preserve]').value.includes('Preserve my ending'));
  assert.ok(f.document.querySelector('#feedback').textContent.includes('Synthetic'));
 }
});

test('ambiguous natural scope requires a local choice, with no preparation/provider call until resolved',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay from the leadership book.';await f.click('Continue');
 assert.equal(f.requests.filter(r=>r.options).length,0);assert.ok(f.nodes().some(n=>n.textContent?.includes('Which materials did you mean?')));
 await f.click('Search across your library');assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
 assert.deepEqual([...f.requests.find(r=>r.path==='/workshops/prepare').options.body.source_ids],[]);
});

test('knowledge question bridge preserves exact question, explicit result type and real material scope',async()=>{
 const f=await fixture('#/create'),form=f.main.querySelector('#create-brief');form.seedInteraction('What does this source teach?\nChapter or section: Focus',['s1']);
 await f.click('Continue');const payload=f.requests.find(r=>r.path==='/workshops/prepare').options.body;
 assert.ok(payload.situation.startsWith('What does this source teach?\nChapter or section: Focus'));assert.equal(payload.output_type,'knowledge_answer');
 assert.deepEqual([...payload.source_ids],['s1']);assert.throws(()=>form.seedInteraction('Question',['invented']),/Choose the materials/);
});

test('implicit Create form submission does not call generation; only explicit Create activation does',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
 let prevented=false;f.main.querySelector('#create-brief').onsubmit({preventDefault(){prevented=true;}});
 assert.ok(prevented);assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
 await f.click('Create essay');assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,1);
});

const visiblyShown=n=>!n.hidden&&(!n.parent||visiblyShown(n.parent))&&(!n.parent||n.parent.tag!=='details'||n.parent.open||n.tag==='summary');
test('detailed Create confirms concise intent and evidence, hides optional schema and developer controls',async()=>{
 const f=await fixture('#/create');const text='Write an essay. Keep my voice. Avoid jargon. Budget: under $200.\nAudience: team leads';
 const input=f.document.querySelector('[name=original_request]');input.value=text;await f.click('Continue');
 const shown=f.nodes().filter(visiblyShown);
 assert.equal(input.value,text);assert.equal(visiblyShown(input),false);
 assert.equal(shown.filter(n=>n.textContent==='Write an essay.').length,1);
 assert.ok(shown.some(n=>n.textContent==='Search scope · Across your library'));
 assert.ok(shown.some(n=>n.textContent?.includes('A book · 1 of 3 sections ready · Partial coverage')));
 assert.ok(shown.some(n=>n.textContent==='1 relevant idea found'));
 assert.ok(!shown.some(n=>['Task','Goal','Audience','Tone / style','Context','Structured output result'].includes(n.textContent)));
 assert.ok(!shown.some(n=>/Gemini|JSON|manual import|Ctrl|Command|All materials/.test(n.textContent||'')));
 const nodes=f.nodes();assert.ok(nodes.indexOf(f.document.querySelector('.source-coverage'))<nodes.indexOf(nodes.find(n=>n.textContent==='Create essay')));
});
test('committed local correction prepares once; typing blocks stale generation and never calls a provider',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
 const input=f.document.querySelector('[name=constraints]');input.value='Under 100 words';input.oninput();
 assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
 await f.click('Create essay');assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
 await input.onchange();assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,2);
 assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
 const revision=f.requests.filter(r=>r.path==='/workshops/prepare').at(-1).options.body.interaction_revision;
 await f.click('Create essay');const generated=f.requests.find(r=>r.path==='/workshops/generate').options.body;
 assert.equal(generated.interaction_revision,revision);assert.equal(generated.prepared_snapshot_id,'server-snapshot-reference-12345');
 assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,2);
});
test('vague Create asks locally for a result then prepares; source controls are accessible checkboxes',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Help me think about better meetings';await f.click('Continue');
 assert.equal(f.requests.filter(r=>r.options).length,0);const mode=f.document.querySelector('[name=output_type]');assert.equal(mode.value,'');
 assert.ok(f.nodes().some(n=>n.textContent==='Result · Needs your input'));
 mode.value='writing';await mode.onchange();assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
 const check=f.document.querySelector('[name=material_s1]');assert.equal(check.type,'checkbox');check.checked=true;await check.onchange();
 assert.deepEqual([...f.requests.filter(r=>r.path==='/workshops/prepare').at(-1).options.body.source_ids],['s1']);
 assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
});
test('result-family changes clear incompatible old formats before refreshing evidence',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an Email about practice breaks';await f.click('Continue');
 assert.equal(f.document.querySelector('[name=output_format]').value,'Email');
 const mode=f.document.querySelector('[name=output_type]');mode.value='knowledge_answer';await mode.onchange();
 const prepared=f.requests.filter(r=>r.path==='/workshops/prepare').at(-1).options.body;
 assert.equal(prepared.output_type,'knowledge_answer');assert.equal(prepared.output_format,null);
 assert.equal(f.document.querySelector('[name=output_format]'),null);
});

test('final CTA uses confirmed format or existing catalogue label; scope and coverage are distinct',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Create essay'));
 assert.ok(f.nodes().some(n=>n.textContent==='Search scope · Across your library'));
 assert.ok(f.nodes().some(n=>n.textContent==='Source coverage'));
 assert.ok(f.nodes().some(n=>n.textContent==='Uses the knowledge shown above.'));
 const format=f.document.querySelector('[name=output_format]');format.value='Email';await format.onchange();
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Create email'));
 const mode=f.document.querySelector('[name=output_type]');mode.value='knowledge_answer';await mode.onchange();
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Create knowledge answer'));
 assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
});
test('expanding the mobile preview is local presentation and preserves every prepared idea',async()=>{
 const f=await fixture('#/create'),original=f.ctx.api;
 const units=Array.from({length:5},(_,i)=>({canonical_asset:{id:'a'+i,title:'Idea '+i},source_ids:['s1']}));
 f.ctx.api=async(path,options)=>{
  const result=await original(path,options);
  return path==='/workshops/prepare'?{...result,knowledge_unit_count:5,knowledge_units:units}:result;
 };
 f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
 const extra=f.nodes().filter(n=>n.className==='preview-idea preview-extra');assert.equal(extra.length,3);
 const count=f.requests.length,revision=vm.runInContext('interactionDraft.revision',f.ctx);
 await f.click('View all 5 ideas');assert.equal(f.document.querySelector('#create-relevant-ideas').className,'preview-ideas expanded');
 assert.equal(f.requests.length,count);assert.equal(vm.runInContext('interactionDraft.revision',f.ctx),revision);
 assert.equal(vm.runInContext('interactionDraft.prepared.evidence.knowledge_units.length',f.ctx),5);
 await f.click('Show fewer ideas');await f.click('Create essay');
 assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
 assert.equal(f.requests.find(r=>r.path==='/workshops/generate').options.body.prepared_snapshot_id,'server-snapshot-reference-12345');
});
