import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {PAGE_SIZE, filterUnits, scopeQuestion, createSearchController} from '../knowledge-browser.js';

test('scope wording follows single or multiple sources',()=>{
 assert.equal(scopeQuestion('What does this source teach?',false),'What do these sources teach?');
 assert.equal(scopeQuestion('What concepts appear in this source?',false),'What concepts appear in these sources?');
 assert.equal(scopeQuestion('What problems does this source help solve?',false),'What problems do these sources help solve?');
 assert.equal(scopeQuestion('What does this source teach?',true),'What does this source teach?');
});
test('new search clears old results and late responses cannot restore them',async()=>{
 const pending=[],shown=[];
 const controller=createSearchController((query,scope)=>new Promise(resolve=>pending.push({query,scope,resolve})),(...args)=>shown.push(args));
 const old=controller.search('old','source-a');
 const current=controller.search('facilitation','source-b');
 assert.deepEqual(shown.at(-1),[[],'loading','facilitation']);
 pending[1].resolve(['relevant']);await current;
 pending[0].resolve(['irrelevant']);await old;
 assert.deepEqual(shown.at(-1),[['relevant'],'results','facilitation']);
 const stale=controller.search('stale','source-a');controller.invalidate();pending[2].resolve(['stale']);await stale;
 assert.deepEqual(shown.at(-1),[[],'idle']);
});
test('search failure clears results and does not restore browse items',async()=>{
 const shown=[];const controller=createSearchController(async()=>{throw Error('offline');},(...args)=>shown.push(args));
 await assert.rejects(controller.search('facilitation',''),/offline/);
 assert.deepEqual(shown.at(-1),[[],'error','facilitation']);
});

// Minimal DOM doubles exercise the real Knowledge view handlers without a browser or network.
class Element {
 constructor(tag,text){this.tag=tag;this.textContent=text;this.children=[];this.value='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[];this.append(...nodes);if(this.tag==='select')this.value=nodes[0]?.value||'';}
 setAttribute(){}
 querySelectorAll(){return [];}
}
function descendants(node){return [node,...node.children.flatMap(descendants)];}
const groups=Array.from({length:25},(_,i)=>({canonical_asset:{id:`a${i}`,title:`Unit ${i}`,what_it_says:'Synthetic evidence',asset_type:i<12?'concept':'principle',chapter_or_section:i<12?'Chapter 1':'Chapter 2'},support_count:1,evidence_trail:[{source_id:'s1',chunk_id:`c${i}`,evidence:'Synthetic evidence'}]}));
async function viewFixture(){
 const main=new Element('main'),requests=[];
 const el=(tag,text)=>new Element(tag,text);
 const ctx={PAGE_SIZE,filterUnits,createSearchController,URLSearchParams,Event,
 main,state:{source:null,library:'lib1',selected:new Set()},el,
 heading(){},sourceItems:async()=>[{id:'s1',title:'First source'}],message(){},navigate(){},
 document:{dispatchEvent(){}},
 run:async fn=>fn(),
 api:async path=>{requests.push(path);return {items:path.startsWith('/knowledge-assets/search')?groups.slice(0,1):groups};},
 field:(label,name)=>{const l=el('label',label),input=el('input');input.name=name;l.append(input);return [l,input];},
 select:(label,options,current='')=>{const l=el('label',label),s=el('select');s.value=current;s.children=options.map(([value,text])=>Object.assign(el('option',text),{value}));l.append(s);return [l,s];},
 form:fn=>Object.assign(el('form'),{submit:fn}),submit:text=>el('button',text),
 card:(title,text)=>{const c=el('section');c.append(el('h3',title),el('p',text));return c;},
 detail:(text,...nodes)=>{const d=el('details');d.append(el('summary',text),...nodes);return d;},
 actions:(...nodes)=>{const d=el('div');d.append(...nodes);return d;},
 button:(text,fn)=>Object.assign(el('button',text),{click:fn}),
 Option:function(text,value){return Object.assign(el('option',text),{value});},
 };
 const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function knowledgeView()'),source.indexOf('async function workshopView()')),ctx);
 await ctx.knowledgeView();return {main,requests,ctx,nodes:()=>descendants(main)};
}
test('browse loads on demand, pages by ten, filters, preserves evidence and selection',async()=>{
 const f=await viewFixture();assert.equal(f.requests.length,0);
 const browse=f.nodes().find(n=>n.id==='ke-browse');browse.open=true;await browse.ontoggle();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,10);
 assert.equal(f.nodes().filter(n=>n.textContent==='Evidence & provenance').length,10);
 await f.nodes().find(n=>n.textContent==='Show more').click();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,20);
 const type=f.nodes().find(n=>n.textContent==='Knowledge type').children[0];type.value='principle';type.onchange();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,10);
 const checkbox=f.nodes().find(n=>n.type==='checkbox');checkbox.checked=true;checkbox.onchange();assert.ok(f.ctx.state.selected.has(checkbox.name));
 const chapter=f.nodes().find(n=>n.textContent==='Chapter / section').children[0];chapter.value='Chapter 1';chapter.onchange();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,0);
});
test('actual view sends consolidated query with scope; edits and scope changes clear search',async()=>{
 const f=await viewFixture();const form=f.nodes().find(n=>n.id==='ke-search-form');const query=f.nodes().find(n=>n.name==='q');const scope=f.nodes().find(n=>n.id==='ke-source-scope');
 scope.value='s1';scope.onchange();query.value='One-on-one facilitation approach';await form.submit();
 const url=new URL(f.requests.at(-1),'http://local');assert.equal(url.pathname,'/knowledge-assets/search');
 assert.equal(url.searchParams.get('q'),query.value);assert.equal(url.searchParams.get('source_id'),'s1');assert.equal(url.searchParams.get('library_id'),'lib1');assert.equal(url.searchParams.get('consolidated'),'true');
 const results=f.nodes().find(n=>n.id==='ke-search-results');assert.equal(results.hidden,false);
 query.oninput();assert.equal(results.hidden,true);assert.equal(results.children.length,0);
 await form.submit();scope.value='';scope.onchange();assert.equal(results.hidden,true);
});

test('chapter and example questions require their relevant context',()=>{
 const text=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
 let source='',chapter='',idea='';const prompts=[];
 const ctx={CHAPTER_QUESTION:'What did this chapter teach?',IDEA_EXAMPLES_QUESTION:'What examples support this idea?',
 document:{querySelector:()=>({value:source})},knowledgeScopeValue:id=>id==='#ke-chapter-scope'?chapter:idea,
 showKnowledgeScopePrompt:(...args)=>prompts.push(args)};
 vm.createContext(ctx);vm.runInContext(text.slice(text.indexOf('function validateKnowledgeQuestionScope('),text.indexOf('function renderKnowledgeAnswer(')),ctx);
 assert.equal(ctx.validateKnowledgeQuestionScope(ctx.CHAPTER_QUESTION),false);
 source='s1';assert.equal(ctx.validateKnowledgeQuestionScope(ctx.CHAPTER_QUESTION),false);
 chapter='Chapter 1';assert.equal(ctx.validateKnowledgeQuestionScope(ctx.CHAPTER_QUESTION),true);
 assert.equal(ctx.validateKnowledgeQuestionScope(ctx.IDEA_EXAMPLES_QUESTION),false);
 idea='Attention';assert.equal(ctx.validateKnowledgeQuestionScope(ctx.IDEA_EXAMPLES_QUESTION),true);
 assert.equal(prompts.length,3);
});
test('late grounded answer cannot render after scope changes',async()=>{
 const text=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
 let resolve;const rendered=[],requests=[];
 const ctx={answerRevision:0,validateKnowledgeQuestionScope:()=>true,selectedKnowledgeSourceIds:()=>['s1','s2'],
 document:{querySelector:()=>({value:''})},scopeQuestion,scopedKnowledgeQuestion:q=>q,
 knowledgeAnswerCard:()=>({isConnected:true,replaceChildren(){}}),makeElement:()=>({}),
 fetch:(url,options)=>{requests.push(JSON.parse(options.body));return new Promise(r=>{resolve=r;});},
 renderKnowledgeAnswer:(...args)=>rendered.push(args)};
 vm.createContext(ctx);vm.runInContext(text.slice(text.indexOf('async function generateKnowledgeAnswer('),text.indexOf('function decorateKnowledgeView(')),ctx);
 const pending=ctx.generateKnowledgeAnswer('What does this source teach?');
 assert.equal(requests[0].situation,'What do these sources teach?');assert.equal(requests[0].save,false);
 ctx.answerRevision++;resolve({ok:true,json:async()=>({output:{content:'Old scope'}})});await pending;
 assert.equal(rendered.length,0);
});
