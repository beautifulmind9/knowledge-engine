import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createNavigation, parseRoute, routeHash} from '../navigation.js';
import {scopeQuestion, PAGE_SIZE, filterUnits, createSearchController} from '../knowledge-browser.js';
import {revisionPayload} from '../output-revision.js';
import * as interaction from '../interaction-draft.js';
import * as materialAdd from '../material-add.js';
import * as knowledgeBuild from '../knowledge-build.js';
import * as materialPreparation from '../material-preparation.js';
import {renderGroundedAnswer, observeAnswerTableOverflow} from '../answer-renderer.js';
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
 scrollIntoView(){}
}
function matches(n,selector){const attr=selector.match(/\[([^=]+)=['"]?([^'"\]]+)['"]?\]/);if(attr&&String(n[attr[1]])!==attr[2])return false;selector=selector.replace(/\[.*?\]/,'');const id=selector.match(/#([\w-]+)/),cls=selector.match(/\.([\w-]+)/),tag=selector.match(/^[\w-]+/);return (!id||n.id===id[1])&&(!cls||n.className?.split(' ').includes(cls[1]))&&(!tag||n.tag===tag[0]);}
const all=n=>[n,...n.children.flatMap(all)];
function browserStub(hash=''){
 const location={hash},entries=[{hash,state:null}],listeners={};let index=0;
 const browser={location,addEventListener(type,fn){(listeners[type]??=[]).push(fn);},async dispatch(type){await Promise.all((listeners[type]||[]).map(fn=>fn()));},history:{
  state:null,pushState(state,_title,next){entries.splice(++index);entries.push({hash:next,state});this.state=state;location.hash=next;},
  replaceState(state,_title,next){entries[index]={hash:next,state};this.state=state;location.hash=next;},
  async back(){if(index){location.hash=entries[--index].hash;this.state=entries[index].state;await Promise.all((listeners.popstate||[]).map(fn=>fn()));}},
  async forward(){if(index<entries.length-1){location.hash=entries[++index].hash;this.state=entries[index].state;await Promise.all((listeners.popstate||[]).map(fn=>fn()));}},
 }};return browser;
}
async function fixture(hash='',authenticated=false,enhance=false){
 const main=new Node('main'),feedback=new Node('div'),processingRegion=new Node('div'),body=new Node('body'),requests=[],browser=browserStub(hash);main.id='main';feedback.id='feedback';processingRegion.id='processing-status';body.append(main,processingRegion,feedback);const nav=['home','library','workshop','outputs','settings'].map(view=>{const n=new Node(view==='home'?'a':'button');n.dataset={view};return n;});
 const source={id:'s1',title:'A book',author:'A writer',library_id:'l1',file_path:'file',processing_status:'uploaded'};
 const audit={interpretation:{completed_chunks:1,total_chunks:3},overlap_rate:0,superseded_assets:[],old_schema_assets:[],missing_evidence:[],missing_keywords:[],evidence_needing_review:[],asset_types:{},confidence_distribution:{},jobs:[{id:'j1',chunk_id:'c1',status:'failed'}]};
 const events=new Map();
 const document={addEventListener(type,fn){const callbacks=events.get(type)||[];callbacks.push(fn);events.set(type,callbacks);},dispatchEvent(event){for(const callback of events.get(event.type)||[])callback(event);},body,querySelector:s=>s==='main'?main:s==='#feedback'?feedback:s==='#processing-status'?processingRegion:body.querySelector(s),querySelectorAll:s=>s==='[data-view]'?nav:s==='nav button'?nav.filter(n=>n.tag==='button'):body.querySelectorAll(s),createElement:tag=>new Node(tag),createTextNode:text=>Object.assign(new Node('#text'),{textContent:String(text)})};
 const ctx={attachProcessingAnnouncer:()=>{},announceProcessingStatus:()=>{},...interaction,...materialAdd,...knowledgeBuild,...materialPreparation,console,URLSearchParams,Event,window:browser,createNavigation,PAGE_SIZE,filterUnits,createSearchController,revisionPayload,renderGroundedAnswer,observeAnswerTableOverflow,subscribeProcessingStatus:()=>()=>{},renderProcessingStatus:()=>{},beginProcessingStatus:()=>1,updateProcessingStatus:()=>true,endProcessingStatus:()=>true,getProcessingStatus:()=>null,processingRegion,Option:function(text,value){const n=new Node('option');n.textContent=text;n.value=value;return n;},FormData:class {constructor(form){this.values=form?all(form).filter(n=>n.name&&!n.disabled&&!(n.type==='checkbox'&&!n.checked)).flatMap(n=>n.tag==='select'?n.selectedOptions.filter(o=>!o.disabled).map(o=>[n.name,o.value]):[[n.name,n.value]]):[];}get(name){return this.values.find(pair=>pair[0]===name)?.[1]||'';}[Symbol.iterator](){return this.values[Symbol.iterator]();}},Set,Map,Date,document,api:async(path,options)=>{requests.push({path,options});if(options){if(path==='/workshops/prepare')return {prepared_snapshot_id:'server-snapshot-reference-12345',interaction_revision:options.body.interaction_revision,source_coverage:[{title:'A book',prepared_sections:1,total_sections:3,relevant_idea_count:1}],knowledge_unit_count:1,knowledge_units:[{canonical_asset:{title:'An idea'},source_ids:['s1']}],synthesis_context:{agreements:[],tensions:[],limitations:''}};if(path==='/workshops/generate')return {saved_output:{id:'new-work'}};if(path.endsWith('/process'))source.chunks_path='chunks';return {processed_this_run:1};}if(path==='/outputs/modes')return {items:[{id:'writing',label:'Writing',formats:['Email','Essay']},{id:'knowledge_answer',label:'Knowledge answer'}]};if(path==='/libraries')return {items:[{id:'l1',name:'Reading'}]};if(path.startsWith('/sources?')||path==='/sources')return {items:[source]};if(path==='/sources/summaries')return [{source_id:'s1',readiness:'partly_ready',completed_parts:1,total_parts:3,coverage_text:'1 of 3 parts ready',has_usable_knowledge:true,operation:'idle',attention_category:null,attention_message:null,file_state:'available',read_state:'read',next_action:'continue_building',recovery:[]}];if(path.endsWith('/summary'))return {has_usable_knowledge:true,readiness:audit.interpretation.completed_chunks===audit.interpretation.total_chunks?'ready':'partly_ready',completed_parts:audit.interpretation.completed_chunks,total_parts:audit.interpretation.total_chunks,coverage_text:`${audit.interpretation.completed_chunks} of ${audit.interpretation.total_chunks} parts ready`,next_action:'continue_building',recovery:[{job_id:'j1',allowed:true}]};if(path.endsWith('/audit'))return audit;if(path.endsWith('/chunks'))return {items:[{id:'c1',chunk_index:1,word_count:100}]};if(path.endsWith('/knowledge-units'))return {items:[{canonical_asset:{title:'An idea',what_it_says:'Useful insight'}}]};if(path==='/sources/s1')return source;if(path.endsWith('/quality'))return {validation_status:'passed',issues:[]};if(path.endsWith('/history'))return {items:[]};if(/^\/outputs\/[^/]+$/.test(path))return {id:path.split('/').at(-1),title:'My essay',content:'The artifact',version:1,output_type:'writing',provider:'manual',applied_knowledge:[],design_choices:[]};if(path==='/usage')return {configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:10};if(path==='/data/integrity')return {ok:true,issues:[]};if(path==='/outputs')return {items:[{id:'o1',title:'My essay',root_output_id:'o1',output_type:'writing',version:1}],count:1};throw Error(path);},csrfToken:()=>authenticated?'fixture-token':null};
 vm.createContext(ctx);vm.runInContext(readFileSync(new URL('../create-draft.js',import.meta.url),'utf8').replaceAll('export ',''),ctx);if(enhance){const extension={document,Event,scopeQuestion,apiFetch:async(path,options)=>({ok:true,json:async()=>ctx.api(path,{...options,body:JSON.parse(options.body)})})};vm.createContext(extension);vm.runInContext(readFileSync(new URL('../enhancements.js',import.meta.url),'utf8').replace(/^import .*;\n/gm,''),extension);}
 vm.runInContext(app.replace(/^import .*;\n/gm,''),ctx);await new Promise(resolve=>setImmediate(resolve));
 return {ctx,main,document,browser,nav,requests,source,audit,nodes:()=>all(main),click:async text=>{const n=all(main).find(n=>(n.tag==='button'||n.tag==='a')&&n.textContent===text);assert.ok(n,text);if(n.onclick)await n.onclick({preventDefault(){}});else if(n.listeners.click)await Promise.all(n.listeners.click.map(fn=>fn()));else await n.closest('form').onsubmit({preventDefault(){}});}};
}
test('Home actions route to Library, Create and My work; shell has task navigation',async()=>{
 const f=await fixture();
 for(const [action,target] of [['Add to my library','library'],['Create something','workshop'],['Continue my work','outputs']]){await f.ctx.navigate('home');await f.click(action);assert.equal(parseRoute(f.browser.location.hash).view,target);}
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
 assert.match(html,/data-view="home"/);assert.match(html,/>Library<.*>Create<.*>My work</s);assert.match(html,/>Settings</);assert.doesNotMatch(html,/Local personal beta|<aside|>Knowledge<|>Workshop<|Saved outputs|Data &amp; usage|>Source</);
});
test('Source detail keeps failed-build retry explicit, knowledge first, and evidence readable',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
 f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({source_id:'s1',readiness:'partly_ready',completed_parts:12,total_parts:20,coverage_text:'12 of 20 parts ready',has_usable_knowledge:true,operation:'idle',attention_category:'build_stopped',attention_message:'The previous knowledge-building attempt stopped before completion.',file_state:'available',file_replacement_allowed:false,read_state:'read',next_action:'continue_building',recovery:[{job_id:'j1',category:'failed_build',allowed:true}]}):original(path,options);
 await f.ctx.sourceView('s1');await new Promise(resolve=>setImmediate(resolve));
 assert.equal(f.main.querySelector('h1').textContent,'A book');
 assert.ok(f.nodes().some(n=>n.textContent==='Partly prepared'));
 assert.ok(f.nodes().some(n=>n.textContent==='Preparation paused'));
 assert.ok(f.nodes().some(n=>n.textContent==='Your progress is saved. Existing knowledge remains available.'));
 assert.ok(f.nodes().some(n=>n.textContent==='Ask this source'));
 assert.ok(f.nodes().some(n=>n.textContent==='Explore ideas'));
 assert.ok(f.nodes().some(n=>n.textContent==='Use in Create'));
 const evidence=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Source & evidence');assert.ok(evidence&&!evidence.open);
 let advanced=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Advanced / Developer');assert.equal(advanced,undefined);
 assert.ok(!f.nodes().some(n=>n.tag==='button'&&n.textContent==='Resolve preparation issue'));
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Continue preparing'));
 assert.ok(!f.requests.some(r=>r.path.endsWith('/audit')||r.path.endsWith('/chunks')));
 const ordinaryText=f.nodes().map(n=>n.textContent).filter(Boolean).join('\n');
 assert.ok(!/private-source-id|private-chunk-id|private-asset-id/.test(ordinaryText));
 assert.ok(!f.requests.some(r=>r.path.endsWith('/recover')));
 assert.ok(!f.requests.some(r=>r.path.includes('/interpret')));
 await f.ctx.navigate('developerMaterial',{id:'s1'});advanced=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Advanced / Developer');advanced.open=true;await advanced.ontoggle();assert.ok(all(advanced).some(n=>n.textContent==='Manual knowledge import'));
});
test('source preparation is owned by the app session and survives primary-view navigation without duplicate dispatch',async()=>{
 const f=await fixture();let completed=0,posts=0,release,entered;const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>entered=resolve);let activity=null;
 const original=f.ctx.api;f.ctx.api=async(path,options)=>{
  if(path==='/sources/s1/summary')return {source_id:'s1',readiness:completed===3?'ready':completed?'partly_ready':'ready_to_build',completed_parts:completed,total_parts:3,coverage_text:`${completed} of 3 parts ready`,has_usable_knowledge:completed>0,operation:'idle',attention_category:null,attention_message:null,file_state:'available',read_state:'read',next_action:completed===3?'use_knowledge':completed?'continue_building':'build_knowledge',recovery:[]};
  if(path.includes('/interpret?')){posts++;if(posts===1){entered();await gate;}completed++;return {processed_this_run:1};}
  return original(path,options);
 };
 f.ctx.beginProcessingStatus=details=>{activity={id:1,...details};return 1;};f.ctx.updateProcessingStatus=(id,patch)=>{if(activity?.id===id)activity={...activity,...patch};return true;};f.ctx.endProcessingStatus=()=>{activity=null;return true;};f.ctx.getProcessingStatus=()=>activity;
 await f.ctx.navigate('material',{id:'s1'});const continueButton=f.nodes().find(n=>n.tag==='button'&&n.textContent==='Continue preparing');assert.ok(continueButton);const pending=continueButton.onclick();await started;
 const coordinator=vm.runInContext('foregroundBuild',f.ctx),runId=activity.id;
 for(const [view,heading] of [['library','Your library'],['workshop','What are you working on?'],['outputs','Work worth coming back to.'],['settings','Your data, in your hands.'],['library','Your library'],['material','A book']]){
  await f.ctx.navigate(view,{id:view==='material'?'s1':undefined});assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,heading);assert.equal(vm.runInContext('foregroundBuild',f.ctx),coordinator);assert.equal(activity.id,runId);assert.equal(posts,1);
 }
 assert.ok(f.nodes().some(n=>n.textContent==='Preparing'));assert.equal(f.nodes().some(n=>n.textContent==='Continue preparing'),false);
 release();await pending;assert.equal(posts,3);assert.equal(completed,3);assert.equal(vm.runInContext('foregroundBuild',f.ctx),null);assert.equal(activity,null);
});
test('pagehide stops foreground continuation and a fresh app instance does not resume it',async()=>{
 const f=await fixture();let release,entered;const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>entered=resolve);let posts=0;
 const original=f.ctx.api;f.ctx.api=async(path,options)=>{if(path.includes('/interpret?')){posts++;entered();await gate;return {processed_this_run:1};}return original(path,options);};
 await f.ctx.navigate('material',{id:'s1'});const action=f.nodes().find(n=>n.tag==='button'&&n.textContent==='Continue preparing');const pending=action.onclick();await started;await f.browser.dispatch('pagehide');release();await pending;
 assert.equal(posts,1);assert.equal(vm.runInContext('foregroundBuild',f.ctx),null);
 const refreshed=await fixture('#/library/material/s1');assert.equal(refreshed.requests.filter(request=>request.path.includes('/interpret?')).length,0);assert.ok(refreshed.nodes().some(node=>node.textContent==='Continue preparing'));
});
test('My work opens stored work and Settings retains usage and backup controls',async()=>{
 const f=await fixture();await f.ctx.savedView();await f.click('Open work');assert.equal(f.browser.location.hash,'#/my-work/o1');
 await f.ctx.settingsView();const text=f.nodes().map(n=>n.textContent).filter(Boolean).join('\n');assert.ok(text.includes('Shared beta allowance'));assert.ok(text.includes('Shared allowance used today: 0 of 10'));assert.ok(text.includes('Shared allowance remaining today: 10'));assert.ok(text.includes('shared across the workspace'));assert.ok(text.includes('do not use this allowance'));assert.ok(text.includes('This workspace is configured to stay within the approved $0 beta policy.'));assert.ok(!/billing is verified|Gemini key|free-project confirmation|AI actions/i.test(text));assert.ok(f.nodes().some(n=>n.href==='/data/export'));assert.ok(text.includes('No integrity check has been run in this session.'));assert.equal(f.requests.filter(r=>r.path==='/data/integrity').length,0);
 await f.click('Check data integrity');assert.equal(f.requests.filter(r=>r.path==='/data/integrity').length,1);assert.ok(f.nodes().some(n=>n.textContent==='No broken record links or missing material files detected.'));
 await f.ctx.settingsView();assert.equal(f.requests.filter(r=>r.path==='/data/integrity').length,1);
});
test('Settings integrity action reports checking and safe failure states',async()=>{
 const f=await fixture();let release;const gate=new Promise(resolve=>release=resolve);const original=f.ctx.api;
 f.ctx.api=async(path,options)=>{if(path==='/data/integrity'){await gate;throw Error('private storage detail');}return original(path,options);};
 await f.ctx.settingsView();const pending=f.click('Check data integrity');assert.ok(f.nodes().some(n=>n.textContent==='Checking data integrity…'));release();await pending;
 assert.ok(f.nodes().some(n=>n.textContent==='The integrity check could not be completed. Try again.'));
 assert.ok(!f.nodes().some(n=>n.textContent?.includes('private storage detail')));
});
test('an explicit integrity check finishes visibly after returning to Settings',async()=>{
 const f=await fixture();let release;const gate=new Promise(resolve=>release=resolve);const original=f.ctx.api;let calls=0;
 f.ctx.api=async(path,options)=>{if(path==='/data/integrity'){calls++;await gate;return {ok:true,issues:[]};}return original(path,options);};
 await f.ctx.settingsView();const pending=f.click('Check data integrity');await f.ctx.settingsView();
 assert.ok(f.nodes().some(n=>n.textContent==='Checking data integrity…'));release();await pending;
 assert.equal(calls,1);assert.ok(f.nodes().some(n=>n.textContent==='No broken record links or missing material files detected.'));
});
test('Create previews retrieved ideas and sends explicit selections; picker preserves the brief',async()=>{
 const f=await fixture();vm.runInContext("state.selected.add('idea1');state.source='s1';state.library='l1'",f.ctx);
 await f.ctx.workshopView();const situation=f.nodes().find(n=>n.name==='original_request');situation.value='Write a thoughtful essay';
 await f.click('Continue');const preview=f.requests.find(r=>r.path==='/workshops/prepare');assert.deepEqual([...preview.options.body.asset_ids],['idea1']);assert.deepEqual([...preview.options.body.source_ids],['s1']);assert.equal(preview.options.body.situation,situation.value);
 assert.ok(f.nodes().some(n=>n.textContent==='1 relevant idea found'));
 await f.click('Choose ideas myself');assert.equal(parseRoute(f.browser.location.hash).view,'knowledge');await f.click('Use selected ideas in Create');assert.equal(f.nodes().find(n=>n.name==='original_request').value,'Write a thoughtful essay');
 await f.click('Create essay');await new Promise(resolve=>setImmediate(resolve));assert.equal(f.browser.location.hash,'#/my-work/new-work?library=l1');assert.ok(f.requests.some(r=>r.path==='/workshops/generate'));
});
test('Stored work shows artifact first, expandable evidence, history, compare and revision',async()=>{
 const f=await fixture();const requests=[];
 f.ctx.api=async(path,options)=>{requests.push({path,options});if(path==='/sources')return {items:[{id:'source-secret',title:'Facilitator notes'}]};if(path.endsWith('/quality'))return {validation_status:'passed',issues:[]};if(path.endsWith('/history'))return {items:[{id:'o1',version:1},{id:'o2',version:2}]};if(path.includes('/compare/'))return {changed_fields:['content'],content_diff:'An edit'};if(path.endsWith('/revise'))return {id:'o2',version:2};return {id:'o1',title:'My essay',content:'The artifact',output_type:'writing',version:1,provider:'manual',applied_knowledge:[{asset_id:'asset-secret',usage_note:'Used to guide the exercise.'},{asset_id:'asset-without-title',usage_note:'A second grounded reference.'}],knowledge_snapshot:[{canonical_asset:{id:'asset-secret',title:'Practice breaks'},evidence_trail:[{source_id:'source-secret',chunk_id:'chunk-secret',chapter_or_section:'Workshop 2',evidence:'Leave a pause after each exercise.'}]}],design_choices:[]};};
 f.ctx.revisionPayload=()=>({instruction:'Revise'});await f.ctx.outputView('o1');
 const article=f.nodes().find(n=>n.tag==='article');assert.equal(all(article).map(n=>n.textContent||'').join(''),'The artifact');const evidence=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Ideas and evidence used');assert.ok(f.main.children.indexOf(article)<f.main.children.indexOf(evidence));assert.ok(!evidence.open);
 const visibleText=f.nodes().map(n=>n.textContent).filter(Boolean).join('\n');assert.ok(visibleText.includes('Practice breaks'));assert.ok(visibleText.includes('Knowledge used'));assert.ok(visibleText.includes('Facilitator notes · Workshop 2'));assert.ok(visibleText.includes('Leave a pause after each exercise.'));assert.ok(!/asset-secret|asset-without-title|source-secret|chunk-secret/.test(visibleText));
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
test('Library joins compact summary facts and never trusts legacy processing fields',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.processing_status='extraction_failed';f.source.stopped_reason='stale legacy failure';
 const facts={source_id:'s1',readiness:'partly_ready',completed_parts:12,total_parts:20,coverage_text:'12 of 20 parts ready',has_usable_knowledge:true,operation:'idle',attention_category:'build_stopped',attention_message:'The previous knowledge-building attempt stopped before completion.',file_state:'available',read_state:'read',next_action:'continue_building',recovery:[]};
 f.ctx.api=(path,options)=>{if(path==='/sources/summaries'){f.requests.push({path,options});return Promise.resolve([facts]);}return original(path,options);};
 await f.ctx.navigate('library');
 const text=f.nodes().map(n=>n.textContent).filter(Boolean).join('\n');
 assert.ok(text.includes('Partly ready'));assert.ok(text.includes('Partly prepared'));
 assert.ok(text.includes('Needs attention · Progress saved'));
 assert.ok(!/Preparing|Not prepared|Ready to use|stale legacy failure/.test(text));
 assert.ok(f.requests.some(r=>r.path==='/sources/summaries'));
 assert.ok(!f.requests.some(r=>/\/audit|\/chunks|knowledge-units/.test(r.path)));
 assert.equal(f.nodes().some(n=>n.textContent==='Writers'),false);
 assert.equal(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Explore'),true);
});
test('Library state mapping uses one contextual primary action and preserves source scope on Explore',async()=>{
 const cases=[
  ['added','unattached','attach_file',false,'Finish adding'],
  ['added','available','read_source',false,'Read source'],
  ['ready_to_build','available','build_knowledge',false,'Open material'],
  ['partly_ready','available','continue_building',false,'Open material'],
  ['partly_ready','available','continue_building',true,'Explore'],
  ['ready','available','use_knowledge',true,'Explore'],
  ['ready','available','use_knowledge',false,'Open material'],
  ['unknown','unknown','restore_source',true,'Explore'],
  ['unknown','unknown','restore_source',false,'Open material'],
 ];
 for(const [readiness,file_state,next_action,usable,label] of cases){
  const f=await fixture(),original=f.ctx.api,summary={source_id:'s1',readiness,completed_parts:readiness==='unknown'?null:readiness==='ready'?3:readiness==='partly_ready'?1:0,total_parts:readiness==='unknown'?null:3,coverage_text:readiness==='unknown'?null:readiness==='ready'?'3 of 3 parts ready':readiness==='partly_ready'?'1 of 3 parts ready':readiness==='ready_to_build'?'0 of 3 parts ready':null,has_usable_knowledge:usable,operation:'idle',attention_category:null,attention_message:null,file_state,read_state:'read',next_action,recovery:[]};
  f.ctx.api=(path,options)=>path==='/sources/summaries'?Promise.resolve([summary]):original(path,options);
  await f.ctx.navigate('library');
  const row=f.nodes().find(n=>n.tag==='article'&&n.className==='library-row');
  const buttons=row.children.flatMap(n=>n.tag==='div'&&n.className==='actions'?n.children:[]).filter(n=>n.tag==='button');
  assert.equal(buttons[0].textContent,label,`${readiness}/${usable}`);assert.equal(buttons[0].className,'primary');
  assert.equal(buttons.filter(n=>n.className==='primary').length,1);
  const openLinks=all(row).filter(n=>n.tag==='a'&&n.textContent==='Open material');
  assert.equal(openLinks.length,label==='Explore'?1:0,`${readiness}/${usable} uses one contextual action and a quiet material link`);
  if(readiness==='ready'&&!usable)assert.ok(all(row).some(n=>n.textContent==='No usable knowledge is available from this material yet.'));
  if(label==='Explore'){
   await f.click(label);const route=parseRoute(f.browser.location.hash);
   assert.equal(route.view,'knowledge');assert.equal(route.source,'s1');assert.deepEqual(route.materials,['s1']);assert.equal(route.library,'l1');
   assert.ok(!f.requests.some(r=>r.options));
  }else if(label==='Read source'){
   await f.click(label);assert.equal(f.requests.filter(r=>r.path==='/sources/s1/process'&&r.options?.method==='POST').length,1);
   assert.equal(f.requests.filter(r=>r.path==='/sources/s1/interpret?max_chunks=1'&&r.options?.method==='POST').length,2);
  }
 }
});
test('Library does not invent coverage or author and falls back safely when summary loading fails',async()=>{
 for(const mode of ['unknown','failure','no-author']){
  const f=await fixture(),original=f.ctx.api;f.source.author=mode==='no-author'?'':null;
  f.ctx.api=(path,options)=>{if(path==='/sources/summaries'){f.requests.push({path,options});return mode==='failure'?Promise.reject(Error('offline')):Promise.resolve([{source_id:'s1',readiness:'unknown',completed_parts:null,total_parts:null,coverage_text:null,has_usable_knowledge:false,operation:'idle',attention_category:mode==='unknown'?'artifact_unavailable':null,attention_message:mode==='unknown'?'Source data is unavailable.':null,file_state:'unknown',read_state:'unavailable',next_action:'restore_source',recovery:[]}]);}return original(path,options);};
  if(mode==='failure')f.source.processing_status='knowledge_interpreted';
  await f.ctx.navigate('library');const row=f.nodes().find(n=>n.tag==='article'&&n.className==='library-row'),text=all(row).map(n=>n.textContent).filter(Boolean).join('\n');
  assert.ok(text.includes(mode==='failure'?'Readiness unavailable':'Status unavailable'));
  assert.ok(text.includes('Preparation progress unavailable'));assert.ok(!text.includes('0 of 0'));
  assert.ok(!text.includes('Your material'));assert.ok(!text.includes('A writer'));
  if(mode==='failure')assert.ok(text.includes('Current status could not be loaded.'));
  else if(mode==='unknown')assert.ok(text.includes('Needs attention: Source data is unavailable.'));
  else assert.ok(!text.includes('Needs attention:'));
  assert.ok(all(row).some(n=>n.tag==='button'&&n.textContent==='Open material'));
 }
});
test('Empty Library puts Add material before secondary organization and exploration',async()=>{
 const f=await fixture(),original=f.ctx.api;f.ctx.api=(path,options)=>path==='/libraries'&&!options?Promise.resolve({items:[]}):original(path,options);
 await f.ctx.navigate('library');
 const add=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Add material');
 assert.ok(add.open);const collection=f.nodes().find(n=>n.className==='library-collection');assert.ok(collection.children.indexOf(add)<collection.children.findIndex(n=>n.tag==='p'&&n.id==='library-empty'));
 assert.ok(f.nodes().some(n=>n.textContent==='Choose a file to add material to your library. You can organize it into libraries later.'));
 const organization=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Create a library');assert.ok(organization&&!organization.open);
 assert.equal(f.nodes().some(n=>n.name==='Filter by library'),false);
 assert.equal(f.requests.filter(r=>r.options).length,0);
});
test('Library only exposes a library filter when there are multiple destinations',async()=>{
 const f=await fixture(),original=f.ctx.api;f.ctx.api=(path,options)=>path==='/libraries'&&!options?Promise.resolve({items:[{id:'l1',name:'Reading'},{id:'l2',name:'Workshop'}]}):original(path,options);
 await f.ctx.navigate('library');const filter=f.nodes().find(n=>n.name==='Filter by library');assert.ok(filter);
 assert.deepEqual(filter.children.map(option=>option.value),['','l1','l2']);assert.equal(filter.children[0].textContent,'All libraries');
 assert.ok(!f.nodes().some(n=>n.textContent==='Across your library'));
});
test('delayed view loads cannot append controls or headings after navigation to Home',async()=>{
 for(const [view,path] of [['library','/libraries'],['library','/sources'],['material','/sources/s1'],['material','/sources/s1/summary'],['material','/sources/s1/knowledge-units'],['workshop','/outputs/modes'],['outputs','/outputs'],['work','/outputs/o1'],['work','/outputs/o1/quality'],['work','/outputs/o1/history'],['settings','/usage']]){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='chunks';let release;
  f.ctx.api=(url,options)=>url===path?new Promise(resolve=>{release=async()=>resolve(await original(url,options));}):original(url,options);
  const pending=f.ctx.navigate(view,{id:view==='material'?'s1':'o1'});await settle();assert.ok(release,`${view} ${path}`);
  await f.ctx.navigate('home');await release();await pending;
  assert.deepEqual(f.main.children.map(n=>n.tag),['div','h1','p','section','div'],`${view} ${path}`);assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'What would you like to do?');assert.equal(f.main.attributes['aria-busy'],undefined);
 }
});
test('Create navigation round-trip restores core, format and creator fields; clear selection preserves edits',async()=>{
 const f=await fixture();await f.ctx.navigate('workshop');f.document.querySelector('[name=original_request]').value='An intimate essay';await f.click('Continue');
 const values={situation:'An intimate essay',goal:'Explain my experience',audience:'Friends',constraints:'Keep the pauses',tone_or_style:'Personal',output_format:'Email',creative_intent:'Imperfect',creator_context:'A personal memory',preserve:'My voice\nLong pause',avoid:'Jargon'};
 for(const [name,value] of Object.entries(values))f.document.querySelector(`[name="${name}"]`).value=value;
 vm.runInContext("state.selected.add('a1')",f.ctx);await f.click('Clear idea selection');assert.equal(f.document.querySelector('[name="situation"]').value,values.situation);
 await f.click('Choose ideas myself');await f.click('Use this scope in Create');
 for(const [name,value] of Object.entries(values))assert.equal(f.document.querySelector(`[name="${name}"]`).value,value,name);
 assert.ok(!f.browser.location.hash.includes('intimate'));await f.ctx.navigate('settings');await f.browser.history.back();assert.equal(f.document.querySelector('[name="creative_intent"]').value,values.creative_intent);
});
test('chosen material subset bounds picker search/browse and stays consistent on return and refresh',async()=>{
 const f=await fixture(),original=f.ctx.api;
 const sources=[f.source,{...f.source,id:'s2',title:'Second book'},{...f.source,id:'s3',title:'Excluded book'},{...f.source,id:'s4',library_id:'l2',title:'Other library'}];
 f.ctx.api=(path,options)=>{if(!options&&(path==='/sources'||path.startsWith('/sources?')))return Promise.resolve({items:sources});if(path.startsWith('/knowledge-assets/search?')){f.requests.push({path});return Promise.resolve({items:[]});}return original(path,options);};
 await f.ctx.navigate('workshop',{library:'l1',materials:['s1','s2']});f.document.querySelector('[name="original_request"]').value='Write an essay using chosen books';await f.click('Continue');
 await f.click('Choose ideas myself');const scope=f.document.querySelector('#ke-source-scope');assert.deepEqual(scope.options.map(o=>o.value),['','s1','s2']);assert.equal(scope.value,'');
 f.document.querySelector('[name="q"]').value='useful ideas';await f.click('Find matching ideas');const searches=f.requests.filter(r=>r.path.startsWith('/knowledge-assets/search?'));assert.deepEqual(searches.map(r=>new URLSearchParams(r.path.split('?')[1]).get('source_id')),['s1','s2']);
 const browse=f.document.querySelector('#ke-browse');browse.open=true;await browse.ontoggle();assert.ok(!f.requests.some(r=>r.path==='/sources/s3/knowledge-units'));
 scope.value='s2';scope.onchange();vm.runInContext("state.selected.add('idea-from-s2')",f.ctx);await f.click('Use this scope in Create');
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
 const f=await fixture();const original=f.ctx.api;let release;
 f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'added',has_usable_knowledge:false,file_state:'available',file_replacement_allowed:true,read_state:'read_failed',next_action:'read_source',recovery:[]}):original(path,options);
 await f.ctx.navigate('material',{id:'s1'});
 f.ctx.api=(path,options)=>path==='/sources/s1/process'?new Promise(resolve=>{release=async()=>resolve(await original(path,options));}):original(path,options);
 const pending=f.click('Read and prepare material');await f.ctx.navigate('home');await release();await pending;
 assert.equal(f.nodes().find(n=>n.tag==='h1').textContent,'What would you like to do?');assert.equal(f.document.querySelector('#feedback').textContent,'');
});
test('hash changes restore views once, preserve skip-to-content, and restore saved artifact details',async()=>{
 const articleText=f=>all(f.nodes().find(n=>n.tag==='article')).map(n=>n.textContent||'').join('');
 const f=await fixture();f.browser.location.hash='#/my-work/o1';await f.browser.dispatch('popstate');const count=f.requests.length;await f.browser.dispatch('hashchange');assert.equal(f.requests.length,count);assert.equal(articleText(f),'The artifact');assert.equal(f.nav.find(n=>n.dataset.view==='outputs').attributes['aria-current'],'page');
 const refreshed=await fixture(f.browser.location.hash);assert.equal(articleText(refreshed),'The artifact');
 f.browser.location.hash='#main';await f.browser.dispatch('hashchange');assert.equal(articleText(f),'The artifact');
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
 const f=await fixture('#/create'),form=f.main.querySelector('#create-brief');await form.seedInteraction('What does this source teach?\nChapter or section: Focus',['s1']);
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
 assert.ok(shown.some(n=>n.textContent?.includes('A book · Partly prepared · 1 relevant idea')));
 assert.ok(!shown.some(n=>/sections ready|Section coverage unavailable/.test(n.textContent||'')));
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

test('Home carries exact natural text to either destination without execution or URL disclosure',async()=>{
 for(const target of ['Ask & Explore','Create something']){
  const f=await fixture(),request='  Write an essay about practice.\nKeep my exact wording.  ';
  const input=f.document.querySelector('[name=home_request]');input.value=request;input.oninput();await f.click(target);
  assert.equal(f.document.querySelector(target==='Ask & Explore'?'[name=q]':'[name=original_request]').value,request);
  assert.equal(f.requests.filter(r=>r.options).length,0);assert.ok(!f.browser.location.hash.includes('wording'));
  assert.deepEqual(Object.keys(f.browser.history.state),['keEntry']);
  await f.browser.history.back();assert.equal(f.document.querySelector('[name=home_request]').value,request);
  await f.browser.history.forward();assert.equal(f.document.querySelector(target==='Ask & Explore'?'[name=q]':'[name=original_request]').value,request);
 }
});
test('Home handoff protects an interpreted Create draft, Keep preserves snapshot, Replace starts natural capture',async()=>{
 for(const choice of ['Keep current draft','Use new request']){
  const f=await fixture('#/create');const input=f.document.querySelector('[name=original_request]');input.value='Write my existing essay';await f.click('Continue');
  const original=vm.runInContext('interactionDraft',f.ctx);await f.ctx.navigate('home');
  const home=f.document.querySelector('[name=home_request]');home.value='Write a new essay';home.oninput();await f.click('Create something');
  assert.equal(vm.runInContext('interactionDraft',f.ctx),original);assert.ok(f.document.querySelector('#create-handoff'));
  const calls=f.requests.filter(r=>r.options).length;await f.click(choice);
  assert.equal(f.document.querySelector('[name=original_request]').value,choice==='Keep current draft'?'Write my existing essay':'Write a new essay');
  assert.equal(f.requests.filter(r=>r.options).length,calls);
  if(choice==='Keep current draft')assert.equal(vm.runInContext('interactionDraft.prepared',f.ctx),original.prepared);
  else assert.ok(f.nodes().some(n=>n.textContent==='Continue'));
 }
});
test('Library exploration is library-wide while source entry remains scoped; legacy picker routes work',async()=>{
 const f=await fixture('#/library?library=l1');await f.click('Ask & Explore');assert.equal(parseRoute(f.browser.location.hash).view,'knowledge');
 assert.equal(parseRoute(f.browser.location.hash).library,'l1');assert.deepEqual(parseRoute(f.browser.location.hash).materials,[]);
 assert.equal(f.nav.find(n=>n.dataset.view==='library').attributes['aria-current'],'page');
 await f.ctx.navigate('knowledge',{library:'l1',materials:['s1'],source:'s1'});assert.equal(f.document.querySelector('#ke-source-scope').value,'s1');
 assert.equal(parseRoute('#/create/ideas?material=s1').picker,true);assert.equal(parseRoute('#/create/ideas').view,'knowledge');
 assert.equal(f.requests.filter(r=>r.options).length,0);
});
test('independent exploration handoff carries exact query, scope and selections; protects existing draft',async()=>{
 for(const existing of [false,true])for(const selected of [false,true]){
  const f=await fixture(existing?'#/create':'#/home');if(existing){f.document.querySelector('[name=original_request]').value='Old request';await f.ctx.navigate('library');}
  if(selected)vm.runInContext("state.selected.add('idea1')",f.ctx);
  await f.ctx.navigate('knowledge',{library:'l1',materials:['s1'],source:'s1',selectedIds:selected?['idea1']:[]});
  const q=f.document.querySelector('[name=q]');q.value='Write an essay using practice';q.oninput();
  const label=selected?'Use selected ideas in Create':'Use this scope in Create';assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent===label));
  await f.click(label);if(existing){assert.equal(vm.runInContext('interactionDraft.originalRequest',f.ctx),'Old request');await f.click('Use new request');}
  assert.equal(f.document.querySelector('[name=original_request]').value,q.value);
  assert.deepEqual([...vm.runInContext('interactionDraft.scope.value.sourceIds',f.ctx)],['s1']);assert.deepEqual([...vm.runInContext('interactionDraft.scope.value.assetIds',f.ctx)],selected?['idea1']:[]);
  assert.equal(f.requests.filter(r=>r.options).length,0);
 }
});
test('Create picker returns without a replacement decision and retains original request',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write my original essay';await f.click('Continue');await f.click('Choose ideas myself');
 const q=f.document.querySelector('[name=q]');q.value='Different search terms';q.oninput();await f.click('Use this scope in Create');
 assert.equal(f.document.querySelector('[name=original_request]').value,'Write my original essay');assert.equal(f.document.querySelector('#create-handoff'),null);
});
test('Back and Forward restore distinct exploration queries on the same scoped route',async()=>{
 const f=await fixture();for(const request of ['First request','Second request']){
  const home=f.document.querySelector('[name=home_request]');home.value=request;home.oninput();await f.click('Ask & Explore');await f.ctx.navigate('home');
 }
 await f.browser.history.back();assert.equal(f.document.querySelector('[name=q]').value,'Second request');
 await f.browser.history.back();await f.browser.history.back();assert.equal(f.document.querySelector('[name=q]').value,'First request');
 await f.browser.history.forward();await f.browser.history.forward();assert.equal(f.document.querySelector('[name=q]').value,'Second request');
 assert.equal(f.requests.filter(r=>r.options).length,0);
});

test('source-only handoff cannot silently change an existing Create scope or evidence',async()=>{
 const f=await fixture('#/create');f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
 const original=vm.runInContext('interactionDraft',f.ctx);await f.ctx.navigate('material',{id:'s1'});
 await f.ctx.openCreate({request:'',library:'l1',materials:['s1'],selectedIds:[]});assert.equal(vm.runInContext('interactionDraft',f.ctx),original);
 await f.click('Keep current draft');assert.equal(vm.runInContext('interactionDraft.prepared',f.ctx),original.prepared);
 assert.deepEqual([...vm.runInContext('interactionDraft.scope.value.sourceIds',f.ctx)],[]);
});
test('Create nav resumes its own scope after visiting another library without invalidating reviewed evidence',async()=>{
 const f=await fixture('#/create?library=l1&material=s1');f.document.querySelector('[name=original_request]').value='Write an essay';await f.click('Continue');
 const original=vm.runInContext('interactionDraft',f.ctx);await f.ctx.navigate('library',{library:null});await f.ctx.navigate('workshop');
 assert.equal(vm.runInContext('interactionDraft.prepared',f.ctx),original.prepared);
 assert.deepEqual([...vm.runInContext('interactionDraft.scope.value.sourceIds',f.ctx)],['s1']);
 assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
});

test('unified exploration keeps optional context hidden and prompt selection local',async()=>{
 const f=await fixture('#/library/explore',false,true);
 assert.equal(f.nodes().filter(n=>n.tag==='textarea').length,1);
 assert.equal(f.nodes().filter(n=>n.name==='knowledge_question').length,0);
 assert.equal(f.document.querySelector('#explore-context').open,false);
 assert.ok(f.nodes().some(n=>n.textContent==='Across your library'));
 assert.ok(!f.nodes().some(n=>n.textContent?.includes('All materials across libraries')));
 await f.click('Ask about a section');
 assert.equal(f.document.querySelector('#explore-context').open,true);
 assert.equal(f.document.querySelector('#ke-idea-scope').closest('label').hidden,true);
 assert.equal(f.requests.filter(r=>r.options).length,0);
 await f.click('Concepts');assert.equal(f.requests.filter(r=>r.options).length,0);
 assert.ok(f.document.querySelector('[name=q]').value.length>2);
});
test('Home destination buttons have equal emphasis and no operational helper',async()=>{
 const f=await fixture();const buttons=['Ask & Explore','Create something'].map(t=>f.nodes().find(n=>n.tag==='button'&&n.textContent===t));
 assert.equal(buttons[0].className,buttons[1].className);
 assert.ok(f.nodes().some(n=>n.textContent==='Choose what you’d like to do with your request.'));
 assert.equal(f.requests.filter(r=>r.options).length,0);
});


test('empty Add rejects locally before creating a source or reporting success',async()=>{
 const f=await fixture('#/library');const file=f.nodes().find(n=>n.name==='file');file.files=[{size:0,name:'empty.txt'}];file.onchange();
 assert.equal(f.requests.filter(r=>r.options).length,0);
 assert.equal(f.document.querySelector('#feedback').textContent,'The uploaded file is empty.');
});
test('source detail shows summary dimensions independently and keeps diagnostics lazy',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
 f.ctx.api=(path,options)=>{
  if(path.endsWith('/summary'))return Promise.resolve({source_id:'s1',readiness:'partly_ready',completed_parts:12,total_parts:20,coverage_text:'12 of 20 parts ready',has_usable_knowledge:true,operation:'idle',attention_category:'build_stopped',attention_message:'The previous knowledge-building attempt stopped before completion.',file_state:'available',file_replacement_allowed:false,read_state:'read',next_action:'continue_building',recovery:[]});
  if(path.endsWith('/audit')||path.endsWith('/chunks')){f.requests.push({path,options});throw Error('Diagnostic failure');}
  return original(path,options);
 };
 await f.ctx.navigate('material',{id:'s1'});
 assert.equal(f.main.querySelector('h1').textContent,'A book');
 assert.ok(f.nodes().some(n=>n.textContent==='Preparation paused'));
 assert.ok(f.nodes().some(n=>n.textContent==='Partly prepared'));
 assert.ok(f.nodes().some(n=>n.textContent==='Your progress is saved. Existing knowledge remains available.'));
 assert.ok(f.nodes().some(n=>n.textContent==='Ask this source'));
 assert.ok(f.nodes().some(n=>n.textContent==='Explore ideas'));
 assert.ok(f.nodes().some(n=>n.textContent==='Use in Create'));
 assert.ok(f.nodes().some(n=>n.textContent==='Continue preparing'));
 assert.ok(!f.nodes().some(n=>n.textContent?.includes('Uses up to')));
 assert.ok(!f.requests.some(r=>r.path.endsWith('/audit')||r.path.endsWith('/chunks')));
 assert.ok(!f.nodes().some(n=>n.textContent==='Advanced / Developer'));
 await f.ctx.navigate('developerMaterial',{id:'s1'});const advanced=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Advanced / Developer');assert.ok(advanced&&!advanced.open);
 advanced.open=true;await advanced.ontoggle();
 assert.match(f.document.querySelector('#feedback').textContent,/Advanced diagnostics could not be loaded/);
 assert.ok(all(advanced).some(n=>n.textContent==='No developer details are available for this material right now.'));
 await f.ctx.navigate('material',{id:'s1'});assert.ok(f.nodes().some(n=>n.textContent==='Ask this source'));
});

test('Advanced / Developer is omitted without prepared parts and remains lazy when available',async()=>{
 const empty=await fixture(),original=empty.ctx.api;empty.source.chunks_path=null;
 empty.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'added',completed_parts:0,total_parts:0,has_usable_knowledge:false,operation:'idle',file_state:'available',read_state:'not_read',next_action:'read_source',recovery:[]}):original(path,options);
 await empty.ctx.navigate('material',{id:'s1'});
 assert.equal(empty.nodes().some(n=>n.tag==='details'&&n.children[0].textContent==='Advanced / Developer'),false);
 assert.equal(empty.requests.some(request=>/\/audit|\/chunks$/.test(request.path)),false);
 const prepared=await fixture(),preparedApi=prepared.ctx.api;prepared.source.chunks_path='parts';
 prepared.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'ready_to_build',completed_parts:0,total_parts:3,has_usable_knowledge:false,operation:'idle',file_state:'available',read_state:'read',next_action:'build_knowledge',recovery:[]}):preparedApi(path,options);
 await prepared.ctx.navigate('material',{id:'s1'});
 assert.ok(!prepared.nodes().some(n=>n.textContent==='Advanced / Developer'));
 await prepared.ctx.navigate('developerMaterial',{id:'s1'});
 const advanced=prepared.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Advanced / Developer');assert.ok(advanced&&!advanced.open);
 assert.equal(prepared.requests.some(request=>/\/audit|\/chunks$/.test(request.path)),false);
});

test('build authorization previews parts and allowance, is bounded, and rechecks before dispatch',async()=>{
 for(const scenario of [
  {completed:2,total:3,allowance:8,expected:'Continue preparing',max:1},
  {completed:12,total:20,allowance:3,expected:'Continue preparing',max:3},
  {completed:0,total:63,allowance:450,expected:'Continue preparing',max:63},
 ]){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
  const summary={readiness:scenario.completed?'partly_ready':'ready_to_build',completed_parts:scenario.completed,total_parts:scenario.total,coverage_text:`${scenario.completed} of ${scenario.total} parts ready`,has_usable_knowledge:scenario.completed>0,operation:'idle',attention_category:null,file_state:'available',file_replacement_allowed:false,read_state:'read',next_action:scenario.completed?'continue_building':'build_knowledge',recovery:[]};
  const usage={configured:true,free_tier_confirmed:true,calls_today:450-scenario.allowance,daily_call_limit:450,paused:false,daily_limit_reached:false};
  f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve(summary):path==='/usage'?Promise.resolve(usage):original(path,options);
  await f.ctx.navigate('material',{id:'s1'});
  const action=f.nodes().find(n=>n.tag==='button'&&n.textContent===scenario.expected);assert.ok(action);
  assert.ok(!f.nodes().some(n=>n.textContent?.includes('Uses up to')));
  await f.click(scenario.expected);
  assert.equal(f.requests.filter(request=>request.path==='/sources/s1/interpret?max_chunks=1'&&request.options?.method==='POST').length,scenario.max);
 }
 const exhausted=await fixture(),original=exhausted.ctx.api;exhausted.source.chunks_path='parts';
 exhausted.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'partly_ready',completed_parts:2,total_parts:3,has_usable_knowledge:false,operation:'idle',file_state:'available',read_state:'read',next_action:'continue_building',recovery:[]}):path==='/usage'?Promise.resolve({configured:true,free_tier_confirmed:true,calls_today:10,daily_call_limit:10,paused:true,daily_limit_reached:true}):original(path,options);
 await exhausted.ctx.navigate('material',{id:'s1'});
 assert.ok(exhausted.nodes().some(n=>n.textContent==='Preparation paused for today.'));
 assert.equal(exhausted.nodes().find(n=>n.tag==='button'&&n.textContent==='Continue preparing').disabled,true);
 assert.equal(exhausted.requests.some(request=>request.options?.method==='POST'&&request.path.includes('/interpret')),false);
});

test('source Ask, Explore and Create preserve source scope and draft protection without provider calls',async()=>{
 const f=await fixture(),original=f.ctx.api;
 f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'partly_ready',has_usable_knowledge:true,file_state:'available',file_replacement_allowed:false,read_state:'read',next_action:'continue_building',recovery:[]}):original(path,options);
 await f.ctx.navigate('material',{id:'s1'});await f.click('Ask this source');
 const route=parseRoute(f.browser.location.hash);assert.equal(route.view,'knowledge');assert.equal(route.source,'s1');assert.deepEqual(route.materials,['s1']);
 assert.equal(f.nodes().find(n=>n.name==='q').value,'What does this material teach?');assert.equal(f.requests.filter(r=>r.options).length,0);
 await f.ctx.navigate('material',{id:'s1'});await f.click('Explore ideas');
 assert.equal(parseRoute(f.browser.location.hash).source,'s1');assert.equal(f.requests.filter(r=>r.options).length,0);
 await f.ctx.navigate('material',{id:'s1'});vm.runInContext("interactionDraft.originalRequest='Keep my current essay'",f.ctx);await f.click('Use in Create');
 assert.ok(f.nodes().some(n=>n.id==='create-handoff'));assert.ok(f.nodes().some(n=>n.textContent==='Keep current draft'));
 await f.click('Keep current draft');assert.equal(parseRoute(f.browser.location.hash).view,'workshop');
 assert.equal(f.nodes().find(n=>n.name==='original_request').value,'Keep my current essay');
 assert.equal(f.requests.filter(r=>r.options).length,0);
});

test('source action hierarchy follows usable knowledge independently of readiness and preview count',async()=>{
 const cases=[
  ['added',false,'read_source','Read and prepare material'],['ready_to_build',false,'build_knowledge','Continue preparing'],
  ['partly_ready',false,'continue_building','Continue preparing'],['partly_ready',true,'continue_building','Ask this source'],
  ['ready',true,'use_knowledge','Ask this source'],['ready',false,'use_knowledge','Open original file'],
  ['unknown',true,'restore_source','Ask this source'],['unknown',false,'restore_source','Open original file'],
 ];
 for(const [readiness,usable,next_action,expected] of cases){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path=readiness==='added'?null:'parts';
  f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness,has_usable_knowledge:usable,completed_parts:readiness==='unknown'?null:readiness==='ready'?20:readiness==='partly_ready'?12:0,total_parts:readiness==='unknown'?null:20,coverage_text:readiness==='unknown'?null:readiness==='ready'?'20 of 20 parts ready':readiness==='partly_ready'?'12 of 20 parts ready':'0 of 20 parts ready',operation:'idle',attention_category:null,attention_message:null,file_state:'available',file_replacement_allowed:false,read_state:'read',next_action,recovery:[]}):original(path,options);
  await f.ctx.navigate('material',{id:'s1'});
  assert.ok(f.nodes().some(n=>(n.tag==='button'||n.tag==='a')&&n.textContent===expected),`${readiness}/${usable}`);
  assert.equal(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Ask this source'),usable);
  assert.equal(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Explore ideas'),usable);
  assert.equal(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Use in Create'),usable);
  if(readiness==='ready'&&!usable)assert.ok(f.nodes().some(n=>n.textContent==='No usable knowledge is available from this material yet.'));
  if(readiness==='partly_ready'&&usable)assert.ok(f.nodes().some(n=>n.textContent==='Continue preparing'));
  assert.equal(f.requests.filter(r=>r.options).length,0);
 }
});

test('unknown source state keeps existing knowledge useful without preparation jargon',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='unavailable-source-data';
 f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'unknown',completed_parts:null,total_parts:null,coverage_text:null,has_usable_knowledge:true,operation:'idle',attention_category:'artifact_unavailable',attention_message:'Source data is unavailable. Restore the source data to continue.',file_state:'unknown',file_replacement_allowed:false,read_state:'unavailable',next_action:'restore_source',recovery:[]}):original(path,options);
 await f.ctx.navigate('material',{id:'s1'});const text=all(f.main).map(n=>n.textContent||'').join('\n');
 assert.ok(text.includes('Status unavailable'));assert.ok(text.includes('Preparation progress unavailable'));
 assert.ok(text.includes('Existing knowledge remains available. Restore the source data to continue preparing.'));
 assert.ok(!text.toLowerCase().includes('build knowledge'));
 for(const label of ['Ask this source','Explore ideas','Use in Create'])assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent===label));
 assert.equal(f.requests.filter(r=>r.options).length,0);
});

test('source knowledge preview exposes collapsed Source & evidence without raw identifiers',async()=>{
 const f=await fixture(),original=f.ctx.api;
 f.ctx.api=(path,options)=>{
  if(path.endsWith('/summary'))return Promise.resolve({readiness:'ready',has_usable_knowledge:true,file_state:'available',file_replacement_allowed:false,read_state:'read',next_action:'use_knowledge',recovery:[]});
  if(path.endsWith('/knowledge-units'))return Promise.resolve({items:[{canonical_asset:{id:'asset-raw',source_id:'source-raw',chunk_id:'chunk-raw',title:'Make room for reflection',what_it_says:'A short explanation of the idea.'},evidence_trail:[{asset_id:'asset-raw',source_id:'source-raw',chunk_id:'chunk-raw',chapter_or_section:'Practice',evidence:'Leave a short pause after each exercise so people can name what changed.'}]}]});
  return original(path,options);
 };
 await f.ctx.navigate('material',{id:'s1'});
 assert.ok(f.nodes().some(n=>n.textContent==='Make room for reflection'));
 assert.ok(f.nodes().some(n=>n.textContent==='Source & evidence'));
 const evidence=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Source & evidence');assert.ok(evidence&&!evidence.open);
 evidence.open=true;assert.ok(all(evidence).some(n=>n.textContent==='A book · Practice'));
 assert.ok(all(evidence).some(n=>n.textContent?.includes('Leave a short pause')));
 assert.ok(!all(f.main).map(n=>n.textContent).join('\n').match(/asset-raw|source-raw|chunk-raw/));
});

test('failed parts offer explicit building without a competing reset, even when allowance is depleted',async()=>{
 for(const usable of [false,true])for(const depleted of [false,true]){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
  f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'partly_ready',has_usable_knowledge:usable,completed_parts:12,total_parts:20,coverage_text:'12 of 20 parts ready',operation:'idle',attention_category:'build_stopped',attention_message:'The previous knowledge-building attempt stopped before completion.',file_state:'available',read_state:'read',next_action:'continue_building',recovery:[{job_id:'failed-part',category:'failed_build',allowed:true}]}):path==='/usage'?Promise.resolve({configured:true,free_tier_confirmed:true,calls_today:depleted?450:0,daily_call_limit:450,daily_limit_reached:depleted,paused:depleted}):original(path,options);
  await f.ctx.navigate('material',{id:'s1'});
  const build=f.nodes().find(n=>n.tag==='button'&&n.textContent===(depleted?'Continue preparing':'Continue preparing'));
  assert.ok(build);assert.equal(!!build.disabled,depleted);
  assert.ok(!f.nodes().some(n=>n.textContent==='Resolve preparation issue'));
  assert.equal(f.nodes().some(n=>n.textContent==='Ask this source'),usable);
  assert.ok(!f.requests.some(r=>r.path.endsWith('/recover')||r.path.includes('/interpret')));
 }
});

test('build outcomes distinguish a finished material, exhausted allowance and saved partial progress',async()=>{
 for(const scenario of ['ready','allowance','failure']){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
  const facts={readiness:'partly_ready',has_usable_knowledge:true,completed_parts:1,total_parts:3,coverage_text:'1 of 3 parts ready',operation:'idle',file_state:'available',read_state:'read',next_action:'continue_building',recovery:[]};
  const usage={configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:scenario==='allowance'?1:450,daily_limit_reached:false};
  let attempts=0;
  f.ctx.api=async(path,options)=>{
   if(path.endsWith('/summary'))return {...facts};
   if(path==='/usage')return {...usage};
   if(path.includes('/interpret')){
    assert.ok(path.endsWith('max_chunks=1'));attempts++;usage.calls_today++;usage.daily_limit_reached=usage.calls_today>=usage.daily_call_limit;
    if(scenario==='failure'&&attempts===2){facts.attention_category='build_stopped';facts.attention_message='The previous knowledge-building attempt stopped before completion.';facts.recovery=[{job_id:'failed-part',category:'failed_build',allowed:true}];return {processed_this_run:0,stopped_reason:'Private provider diagnostics'};}
    facts.completed_parts++;facts.coverage_text=`${facts.completed_parts} of 3 parts ready`;
    if(facts.completed_parts===3){facts.readiness='ready';facts.next_action='use_knowledge';}
    return {processed_this_run:1};
   }
   return original(path,options);
  };
  await f.ctx.navigate('material',{id:'s1'});await f.click(scenario==='allowance'?'Continue preparing':'Continue preparing');
  const outcome=f.main.querySelector('.material-status');assert.ok(outcome);
  assert.equal(outcome.querySelector('h2').textContent,scenario==='ready'?'Ready':'Partly ready');
  const text=all(outcome).map(n=>n.textContent).filter(Boolean).join('\n');
  assert.ok(scenario==='ready'||text.includes('Existing knowledge remains available.'));
  assert.ok(!text.includes('AI actions'));
  assert.ok(!/authoriz|Private provider diagnostics/.test(text));
  assert.equal(attempts,scenario==='allowance'?1:2);
  assert.ok(f.nodes().some(n=>n.textContent==='Partly prepared'||n.textContent==='Prepared'));
  assert.ok(!f.nodes().some(n=>n.textContent==='Resolve preparation issue'));
  if(scenario==='failure'){
   assert.equal(f.nodes().filter(n=>n.textContent==='The previous preparation attempt stopped before completion.').length,0);
   assert.equal(outcome.querySelector('h2').textContent,'Partly ready');
   assert.ok(text.includes('Existing knowledge remains available.'));
   assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Continue preparing'));
  }
 }
});

test('material preview stays stable during each part and refreshes once after a successful run',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
 const facts={readiness:'partly_ready',has_usable_knowledge:true,completed_parts:0,total_parts:3,coverage_text:'0 of 3 parts ready',operation:'idle',file_state:'available',read_state:'read',next_action:'continue_building',recovery:[]};
 let knowledgeCalls=0;const progressAtDispatch=[];
 f.ctx.api=async(path,options)=>{
  if(path.endsWith('/summary'))return {...facts};
  if(path==='/usage')return {configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:450,daily_limit_reached:false};
  if(path.endsWith('/knowledge-units')){knowledgeCalls++;return {items:[{canonical_asset:{title:`Preview ${knowledgeCalls}`}}]};}
  if(path.includes('/interpret?')){progressAtDispatch.push(f.main.querySelector('progress').attributes['aria-valuetext']);facts.completed_parts++;facts.coverage_text=`${facts.completed_parts} of 3 parts ready`;facts.readiness=facts.completed_parts===3?'ready':'partly_ready';facts.next_action=facts.completed_parts===3?'use_knowledge':'continue_building';return {processed_this_run:1};}
  return original(path,options);
 };
 await f.ctx.navigate('material',{id:'s1'});await new Promise(resolve=>setImmediate(resolve));
 const callsOnEntry=knowledgeCalls;assert.equal(callsOnEntry,1,'existing usable knowledge loads on entry');
 await f.click('Continue preparing');
 assert.deepEqual(progressAtDispatch,['0% prepared','33% prepared','67% prepared']);
 assert.equal(f.main.querySelector('.material-coverage').textContent,'Prepared');
 assert.equal(knowledgeCalls,callsOnEntry+1,'only the terminal refresh follows the three chunk summaries');
 assert.ok(f.nodes().some(n=>n.textContent==='Preview 2'));
});

test('partial preparation refreshes preview once at provider, allowance, validation, timeout, uncertainty and status stops',async()=>{
 for(const stop of ['provider_unavailable','daily_allowance','validation_failed','preparation_timeout','uncertain','status_unavailable']){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
  const facts={readiness:'partly_ready',has_usable_knowledge:false,completed_parts:0,total_parts:3,coverage_text:'0 of 3 parts ready',operation:'idle',file_state:'available',read_state:'read',next_action:'build_knowledge',recovery:[]};
  let attempts=0,knowledgeCalls=0,summaryFailureUsed=false;
  f.ctx.api=async(path,options)=>{
   if(path.endsWith('/summary')){if(stop==='status_unavailable'&&attempts===1&&!summaryFailureUsed){summaryFailureUsed=true;throw Error('synthetic summary outage');}return {...facts};}
   if(path==='/usage')return {configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:450,daily_limit_reached:false};
   if(path.endsWith('/knowledge-units')){knowledgeCalls++;return {items:[{canonical_asset:{title:'New preview'}}]};}
   if(path.includes('/interpret?')){
    attempts++;
    if(attempts===1){facts.completed_parts=1;facts.has_usable_knowledge=true;facts.coverage_text='1 of 3 parts ready';facts.readiness='partly_ready';facts.next_action='continue_building';return {processed_this_run:1};}
    if(stop==='uncertain')throw Error('synthetic uncertain transport');
    facts.attention_category='build_stopped';
    const category=stop==='daily_allowance'?'allowance_exhausted':stop==='preparation_timeout'?'request_timed_out':stop;
    return {processed_this_run:0,stopped_reason:'safe synthetic stop',interruption_category:category};
   }
   return original(path,options);
  };
  await f.ctx.navigate('material',{id:'s1'});await f.click('Continue preparing');
  assert.equal(f.main.querySelector('.material-coverage').textContent,stop==='status_unavailable'?'Preparation progress unavailable':'Partly prepared',stop);
  assert.equal(knowledgeCalls,1,`${stop}: initial no-knowledge message needs no request; one terminal preview refresh follows`);
  assert.ok(f.nodes().some(n=>n.textContent==='New preview'),stop);
 }
});

test('explicit preparation stop keeps confirmed progress and performs one terminal preview refresh',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';let stopAction,stopped=false,knowledgeCalls=0;
 const facts={readiness:'ready_to_build',has_usable_knowledge:false,completed_parts:0,total_parts:3,coverage_text:'0 of 3 parts ready',operation:'idle',file_state:'available',read_state:'read',next_action:'build_knowledge',recovery:[]};
 f.ctx.beginProcessingStatus=details=>{stopAction=details.onStop;return 1;};
 f.ctx.api=async(path,options)=>{
  if(path.endsWith('/summary')){if(facts.completed_parts===1&&!stopped){stopped=true;stopAction?.();}return {...facts};}
  if(path==='/usage')return {configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:450,daily_limit_reached:false};
  if(path.endsWith('/knowledge-units')){knowledgeCalls++;return {items:[{canonical_asset:{title:'Stopped preview'}}]};}
  if(path.includes('/interpret?')){facts.completed_parts++;facts.has_usable_knowledge=true;facts.readiness='partly_ready';facts.coverage_text=`${facts.completed_parts} of 3 parts ready`;facts.next_action='continue_building';return {processed_this_run:1};}
  return original(path,options);
 };
 await f.ctx.navigate('material',{id:'s1'});await f.click('Continue preparing');
 assert.equal(facts.completed_parts,1);assert.equal(knowledgeCalls,1);assert.ok(f.nodes().some(n=>n.textContent==='Stopped preview'));
});

test('explicit material knowledge actions remain available after preview deferral',async()=>{
 const f=await fixture();await f.ctx.navigate('material',{id:'s1'});
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Ask this source'));
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Explore ideas'));
 assert.ok(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Use in Create'));
 await f.click('Ask this source');assert.equal(parseRoute(f.browser.location.hash).view,'knowledge');
});

test('navigation away prevents a terminal preview refresh from replacing the current view',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';let release,entered,knowledgeCalls=0,completed=0;
 const gate=new Promise(resolve=>release=resolve),started=new Promise(resolve=>entered=resolve);
 f.ctx.api=async(path,options)=>{
  if(path.endsWith('/summary'))return {source_id:'s1',readiness:completed?'partly_ready':'ready_to_build',has_usable_knowledge:completed>0,completed_parts:completed,total_parts:3,coverage_text:`${completed} of 3 parts ready`,operation:'idle',file_state:'available',read_state:'read',next_action:'continue_building',recovery:[]};
  if(path==='/usage')return {configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:450,daily_limit_reached:false};
  if(path.endsWith('/knowledge-units')){knowledgeCalls++;return {items:[{canonical_asset:{title:'Late preview'}}]};}
  if(path.includes('/interpret?')){entered();await gate;completed++;return {processed_this_run:1};}
  return original(path,options);
 };
 await f.ctx.navigate('material',{id:'s1'});const initialCalls=knowledgeCalls;
 const pending=f.click('Continue preparing');await started;await f.ctx.navigate('library');release();await pending;
 assert.equal(f.main.querySelector('h1').textContent,'Your library');assert.equal(knowledgeCalls,initialCalls);
 assert.ok(!f.nodes().some(n=>n.textContent==='Late preview'));
});

test('source recovery is server-authoritative, explicit, and does not build after reset',async()=>{
 for(const allowed of [false,true]){
  const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';
  f.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'partly_ready',has_usable_knowledge:true,completed_parts:12,total_parts:20,coverage_text:'12 of 20 parts ready',operation:allowed?'build_unconfirmed':'build_unconfirmed',attention_category:allowed?'build_unconfirmed':null,attention_message:allowed?'Previous build has not reported completion.':null,file_state:'available',file_replacement_allowed:false,read_state:'read',next_action:'wait_or_reset',recovery:[{job_id:'job-internal',category:'unconfirmed_build',allowed}]}):original(path,options);
  await f.ctx.navigate('material',{id:'s1'});
  assert.equal(f.nodes().some(n=>n.tag==='button'&&n.textContent==='Resolve preparation issue'),allowed);
  if(!allowed)assert.ok(f.nodes().some(n=>n.textContent==='The previous preparation request has not reported completion. Check again before continuing.'));
  else {await f.click('Resolve preparation issue');assert.ok(f.requests.some(r=>r.path==='/knowledge-extractions/job-internal/recover'&&r.options.method==='POST'));}
  assert.ok(!f.requests.some(r=>r.path.includes('/interpret')));
 }
});

test('OCR and unreadable-source recovery only offer supported replacement/read actions',async()=>{
 const ocr=await fixture(),original=ocr.ctx.api;ocr.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'added',has_usable_knowledge:false,file_state:'available',file_replacement_allowed:true,read_state:'ocr_required',attention_category:'ocr_required',attention_message:'This PDF has no extractable text. OCR is not supported.',next_action:'supply_readable_file',recovery:[]}):original(path,options);
 await ocr.ctx.navigate('material',{id:'s1'});assert.ok(ocr.nodes().some(n=>n.textContent==='Use replacement file'));assert.ok(!ocr.nodes().some(n=>n.textContent==='Read and prepare material'));
 const blocked=await fixture(),blockedApi=blocked.ctx.api;blocked.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'added',has_usable_knowledge:false,file_state:'available',file_replacement_allowed:false,read_state:'ocr_required',attention_category:'ocr_required',attention_message:'OCR is not supported.',next_action:'supply_readable_file',recovery:[]}):blockedApi(path,options);
 await blocked.ctx.navigate('material',{id:'s1'});assert.ok(!blocked.nodes().some(n=>n.name==='file'));assert.ok(blocked.nodes().some(n=>n.textContent?.includes('can’t be replaced after preparation has started')));
 const failed=await fixture(),failedApi=failed.ctx.api;failed.ctx.api=(path,options)=>path.endsWith('/summary')?Promise.resolve({readiness:'added',has_usable_knowledge:false,file_state:'available',file_replacement_allowed:true,read_state:'read_failed',attention_category:'read_failed',attention_message:'This file could not be read.',next_action:'read_source',recovery:[]}):failedApi(path,options);
 await failed.ctx.navigate('material',{id:'s1'});assert.ok(failed.nodes().some(n=>n.tag==='button'&&n.textContent==='Read and prepare material'));
});

test('material capture is file-first, local and cancellable; Create draft survives Add navigation',async()=>{
 const f=await fixture('#/create');const request=f.nodes().find(n=>n.name==='original_request');request.value='Write my existing essay';request.oninput();
 await f.ctx.navigate('library',{add:true});assert.ok(!f.nodes().some(n=>n.name==='title'));
 const file=f.nodes().find(n=>n.name==='file');file.files=[{name:'my_workshop_notes.pdf',size:1500}];file.onchange();
 assert.equal(f.nodes().find(n=>n.name==='title').value,'My workshop notes');assert.ok(f.nodes().some(n=>n.textContent==='Destination · Reading'));
 assert.equal(f.requests.filter(r=>r.options).length,0);assert.ok(f.nodes().findIndex(n=>n.name==='file')<f.nodes().findIndex(n=>n.name==='title'));
 await f.click('Cancel');assert.ok(!f.nodes().some(n=>n.name==='title'));assert.equal(f.requests.filter(r=>r.options).length,0);
 await f.ctx.navigate('workshop');assert.equal(f.nodes().find(n=>n.name==='original_request').value,'Write my existing essay');
});
test('empty account file confirmation creates nothing, shows editable My Library destination and optional author',async()=>{
 const f=await fixture(),original=f.ctx.api;f.ctx.api=(path,options)=>path==='/libraries'&&!options?Promise.resolve({items:[]}):original(path,options);
 await f.ctx.navigate('library',{add:true});assert.ok(!f.nodes().some(n=>n.name==='title'));assert.ok(!f.nodes().some(n=>n.textContent==='Create your first library above, then add material.'));
 const file=f.nodes().find(n=>n.name==='file');file.files=[{name:'The_Workshop-Survival_Guide.docx',size:1000}];file.onchange();
 assert.ok(f.nodes().some(n=>n.textContent==='Destination · My Library'));assert.equal(f.nodes().find(n=>n.name==='title').value,'The Workshop Survival Guide');
 const author=f.nodes().find(n=>n.name==='author');assert.ok(!author.required);assert.equal(author.parent.parent.children[0].textContent,'Optional details');
 assert.equal(f.requests.filter(r=>r.options).length,0);
 await f.browser.history.back();await f.browser.history.forward();assert.equal(f.nodes().find(n=>n.name==='title').value,'The Workshop Survival Guide');
});

// Internal support routing is separate from the ordinary material workspace.
test('internal support route preserves escaped identities and is not a normal navigation destination',()=>{
 const id='source / ü';const route={view:'developerMaterial',id};assert.equal(parseRoute(routeHash(route)).id,id);assert.equal(parseRoute(routeHash(route)).view,'developerMaterial');
 const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');assert.ok(!html.includes('developerMaterial'));
});
test('internal manual import keeps the selected part and strict result endpoint without invoking AI',async()=>{
 const f=await fixture(),original=f.ctx.api;f.source.chunks_path='parts';const writes=[];
 f.ctx.api=async(path,options)=>{
  if(options){writes.push({path,options});if(path==='/knowledge-extractions')return {job:{id:'manual-job'}};if(path==='/knowledge-extractions/manual-job/results')return {status:'completed'};}
  return original(path,options);
 };
 await f.ctx.navigate('developerMaterial',{id:'s1'});
 const advanced=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Advanced / Developer');advanced.open=true;await advanced.ontoggle();
 const result=f.nodes().find(n=>n.name==='result');result.value='{"assets":[]}';
 await result.closest('form').onsubmit({preventDefault(){}});
 assert.equal(writes[0].path,'/knowledge-extractions');assert.equal(writes[0].options.body.chunk_id,'c1');assert.equal(writes[0].options.body.source_id,'s1');
 assert.equal(writes[1].path,'/knowledge-extractions/manual-job/results');assert.equal(writes[1].options.body.assets.length,0);
 assert.ok(!writes.some(r=>/interpret|generate/.test(r.path)));assert.equal(parseRoute(f.browser.location.hash).view,'material');
});

test('stored answers separate cited member evidence from related consolidated context', async()=>{
 const f=await fixture();
 f.ctx.api=async(path)=>{
  if(path==='/sources')return {items:[{id:'source_a',title:'First book'},{id:'source_b',title:'Second book'}]};
  if(path.endsWith('/quality'))return {validation_status:'not_evaluated',issues:[]};
  if(path.endsWith('/history'))return {items:[]};
  return {id:'o1',title:'Synthetic answer',content:'A synthetic answer.',output_type:'knowledge_answer',version:1,provider:'manual',
   applied_knowledge:[{asset_id:'asset_a',usage_note:'Canonical idea.'}],
   reasoning_sections:[{supporting_asset_ids:['asset_b']}],
   knowledge_snapshot:[{canonical_asset:{id:'asset_a',title:'Shared idea',source_id:'source_a'},asset_ids:['asset_a','asset_b'],
    evidence_trail:[{asset_id:'asset_a',source_id:'source_a',evidence:'First evidence.'},
                    {asset_id:'asset_b',source_id:'source_b',evidence:'Second evidence.'}]}],design_choices:[]};
 };
 await f.ctx.outputView('o1');
 const cited=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Source & evidence');
 const context=f.nodes().find(n=>n.tag==='details'&&n.children[0].textContent==='Related consolidated evidence · context');
 const text=n=>all(n).map(item=>item.textContent||'').join(' ');
 assert.ok(text(cited).includes('Second book'));
 assert.ok(text(cited).includes('Second evidence.'));
 assert.ok(!text(cited).includes('First evidence.'));
 assert.ok(text(context).includes('First evidence.'));
});
