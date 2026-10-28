import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {PAGE_SIZE, filterUnits, filterSearchResults, scopeQuestion, createSearchController, ideaEvidenceSummary} from '../knowledge-browser.js';
import {routeHash, parseRoute} from '../navigation.js';

test('scope wording follows single or multiple sources',()=>{
 assert.equal(scopeQuestion('What does this source teach?',false),'What do these sources teach?');
 assert.equal(scopeQuestion('What concepts appear in this source?',false),'What concepts appear in these sources?');
 assert.equal(scopeQuestion('What problems does this source help solve?',false),'What problems do these sources help solve?');
 assert.equal(scopeQuestion('What does this source teach?',true),'What does this source teach?');
});

test('precise multi-term search excludes cards that match only one generic term',()=>{
 const items=[
  {canonical_asset:{id:'exact',title:'One-on-one facilitation approach',what_it_says:'Address individuals rather than the crowd.',keywords:['facilitation']}},
  {canonical_asset:{id:'checklist',title:'Exercise Facilitation Checklist',what_it_says:'Facilitation details for exercises.',keywords:['facilitation']}},
  {canonical_asset:{id:'economic',title:'One economic prioritization approach',what_it_says:'Compare economic delay.',keywords:['economic']}},
 ];
 const results=filterSearchResults(items,'One-on-one facilitation approach');
 assert.deepEqual(results.map(group=>group.canonical_asset.id),['exact']);
});

test('single-term search still supports exploration',()=>{
 const items=[
  {canonical_asset:{id:'a',title:'Workshop facilitation',what_it_says:'Facilitate groups.'}},
  {canonical_asset:{id:'b',title:'Facilitation checklist',what_it_says:'Check facilitation details.'}},
 ];
 assert.deepEqual(filterSearchResults(items,'facilitation').map(group=>group.canonical_asset.id),['a','b']);
});

test('scored results preserve backend order and member-only evidence without a second relevance gate',()=>{
 const memberOnly={canonical_asset:{id:'member',title:'A contextual finding'},relevance_score:6.5,
  matched_terms:['narrative','engagement'],evidence_trail:[{evidence:'Narrative engagement is context dependent.'}]};
 const exactTitle={canonical_asset:{id:'exact',title:'Narrative engagement'},relevance_score:2.4};
 const incidental={canonical_asset:{id:'incidental',title:'Audience seating'},relevance_score:1.1};
 const items=[memberOnly,exactTitle,incidental];
 assert.deepEqual(filterSearchResults(items,'Narrative engagement').map(group=>group.canonical_asset.id),['member','exact','incidental']);
 assert.deepEqual(filterSearchResults(items,'Please explain narrative engagement in detail').map(group=>group.canonical_asset.id),['member','exact','incidental']);
});

test('legacy unscored responses retain member evidence and label reference/material counts precisely',()=>{
 const memberOnly={canonical_asset:{id:'legacy',title:'A contextual finding'},evidence_trail:[{source_id:'s1',evidence:'Narrative engagement.'}]};
 assert.equal(filterSearchResults([memberOnly],'Narrative engagement')[0],memberOnly);
 assert.equal(ideaEvidenceSummary({support_count:1,source_ids:['s1']}),'1 supporting reference · 1 material');
 assert.equal(ideaEvidenceSummary({support_count:3,source_ids:['s1','s1'],evidence_trail:[{source_id:'s2'}]}),'3 supporting references · 2 materials');
 assert.equal(ideaEvidenceSummary({asset_ids:['a','b'],canonical_asset:{source_id:'s1'}}),'2 supporting references · 1 material');
 assert.equal(ideaEvidenceSummary({support_count:1}),'1 supporting reference · material count unavailable');
});

test('new search clears old results and late responses cannot restore them',async()=>{
 const pending=[],shown=[];
 const controller=createSearchController((query,scope)=>new Promise(resolve=>pending.push({query,scope,resolve})),(...args)=>shown.push(args));
 const old=controller.search('old','source-a');
 const current=controller.search('facilitation','source-b');
 assert.deepEqual(shown.at(-1),[[],'loading','facilitation']);
 pending[1].resolve([{canonical_asset:{title:'Facilitation',what_it_says:'Relevant facilitation'}}]);await current;
 pending[0].resolve([{canonical_asset:{title:'Old',what_it_says:'Old'}}]);await old;
 assert.equal(shown.at(-1)[1],'results');
 assert.equal(shown.at(-1)[2],'facilitation');
 assert.equal(shown.at(-1)[0].length,1);
 const stale=controller.search('stale','source-a');controller.invalidate();pending[2].resolve([{canonical_asset:{title:'Stale',what_it_says:'Stale'}}]);await stale;
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
 querySelector(){return null;}
 querySelectorAll(){return [];}
}
function descendants(node){return [node,...node.children.flatMap(descendants)];}
const groups=Array.from({length:25},(_,i)=>({canonical_asset:{id:`a${i}`,title:`Unit ${i}`,what_it_says:'Synthetic evidence',asset_type:i<12?'concept':'principle',chapter_or_section:i<12?'Chapter 1':'Chapter 2'},support_count:1,evidence_trail:[{source_id:'s1',chunk_id:`c${i}`,evidence:'Synthetic evidence'}]}));
async function viewFixture({library='lib1', libs=[{id:'lib1',name:'Reading'}], sources=[{id:'s1',title:'First source',library_id:'lib1'}], materials=[],apiImpl=null}={}){
 const main=new Element('main'),requests=[],notices=[],handoffs=[],events=[];
 const el=(tag,text)=>new Element(tag,text);
 const ctx={explorePicker:false,exploreState:{query:'',type:'',section:'',visible:10},freshExplore:()=>({query:'',type:'',section:'',visible:10}),beginView:()=>()=>true,createMaterials:materials,replaceScope(){},PAGE_SIZE,filterUnits,createSearchController,ideaEvidenceSummary,URLSearchParams,Event,
 main,state:{source:null,library,selected:new Set()},el,
 heading(){},libraries:async()=>libs,sourceItems:async()=>sources,message:m=>notices.push(m),navigate(){},openCreate:scope=>handoffs.push(scope),
 document:{dispatchEvent:e=>events.push(e.type)},
 run:async fn=>fn(),
 api:async path=>{requests.push(path);return apiImpl?apiImpl(path):{items:path==='/sources'?sources:path.startsWith('/knowledge-assets/search')?[{canonical_asset:{id:'search',title:'One-on-one facilitation approach',what_it_says:'Facilitation approach',asset_type:'principle'},support_count:1,evidence_trail:[]}]:groups};},
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
 await ctx.knowledgeView();return {main,requests,notices,handoffs,events,ctx,nodes:()=>descendants(main)};
}
test('browse loads on demand, pages by ten, filters, preserves evidence and selection',async()=>{
 const f=await viewFixture();assert.deepEqual(f.requests,['/sources']);
 const browse=f.nodes().find(n=>n.id==='ke-browse');browse.open=true;await browse.ontoggle();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,10);
 assert.equal(f.nodes().filter(n=>n.textContent==='Source & evidence').length,10);
 await f.nodes().find(n=>n.textContent==='Show more').click();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,20);
 const type=f.nodes().find(n=>n.textContent==='Idea type').children[0];type.value='principle';type.onchange();
 assert.equal(f.nodes().filter(n=>n.tag==='h3').length,10);
 const checkbox=f.nodes().find(n=>n.type==='checkbox'&&n.name?.startsWith('a'));checkbox.checked=true;checkbox.onchange();assert.ok(f.ctx.state.selected.has(checkbox.name));
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

test('Find pages scored ideas without losing later selection, query, source evidence or Create scope',async()=>{
 const scored=groups.map((group,index)=>({...group,source_ids:['s1'],relevance_score:groups.length-index,
  matched_terms:['narrative'],evidence_trail:[{source_id:'s1',evidence:'A source-specific supporting excerpt.'}]}));
 const f=await viewFixture({apiImpl:async path=>({items:path==='/sources'?[{id:'s1',title:'First source',library_id:'lib1'}]:scored})});
 const input=f.nodes().find(node=>node.name==='q');input.value='Narrative engagement';input.oninput();
 await f.nodes().find(node=>node.id==='ke-search-form').submit();
 const panel=f.nodes().find(node=>node.id==='ke-search-results');
 assert.equal(descendants(panel).filter(node=>node.tag==='h3').length,10);
 assert.equal(descendants(panel).find(node=>node.tag==='h3').textContent,'Unit 0');
 assert.ok(descendants(panel).some(node=>node.textContent==='Word matches: narrative'));
 assert.ok(descendants(panel).some(node=>node.textContent==='concept · 1 supporting reference · 1 material'));
 await descendants(panel).find(node=>node.textContent==='Show more matching ideas').click();
 assert.equal(descendants(panel).filter(node=>node.tag==='h3').length,20);
 const checked=descendants(panel).find(node=>node.name==='a14');checked.checked=true;checked.onchange();
 f.main.captureExplore();
 await f.nodes().find(node=>node.textContent==='Use selected ideas in Create').click();
 assert.deepEqual([...f.handoffs[0].selectedIds],['a14']);
 assert.deepEqual([...f.handoffs[0].materials],['s1']);
 assert.equal(f.handoffs[0].request,input.value);
 assert.equal(f.ctx.exploreState.searchVisible,20);
 assert.ok(f.requests.every(path=>!path.includes('/workshops/generate')));
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
 const ctx={answerRevision:0,validateKnowledgeQuestionScope:()=>true,selectedKnowledgeSourceIds:()=>['s1','s2'],beginProcessingStatus:()=>1,endProcessingStatus:()=>{},announceProcessingStatus:()=>{},
 document:{querySelector:()=>({value:''})},scopeQuestion,scopedKnowledgeQuestion:q=>q,
 detail:()=>({}),knowledgeAnswerCard:()=>({isConnected:true,replaceChildren(){},setAttribute(){},removeAttribute(){}}),makeElement:()=>({}),
 apiFetch:(url,options)=>{requests.push(JSON.parse(options.body));return new Promise(r=>{resolve=r;});},
 renderKnowledgeAnswer:(...args)=>rendered.push(args)};
 vm.createContext(ctx);vm.runInContext(text.slice(text.indexOf('async function generateKnowledgeAnswer('),text.indexOf('function decorateKnowledgeView(')),ctx);
 const pending=ctx.generateKnowledgeAnswer('What does this source teach?');
 assert.equal(requests[0].situation,'What do these sources teach?');assert.equal(requests[0].save,false);
 ctx.answerRevision++;resolve({ok:true,json:async()=>({output:{content:'Old scope'}})});await pending;
 assert.equal(rendered.length,0);
});

test('Ask sends the question without injecting boilerplate retrieval terms',async()=>{
 const src=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
 const requests=[];
 const ctx={answerRevision:0,validateKnowledgeQuestionScope:()=>true,selectedKnowledgeSourceIds:()=>['creator_a','psychology'],beginProcessingStatus:()=>1,endProcessingStatus:()=>{},announceProcessingStatus:()=>{},
 document:{querySelector:()=>({value:''})},scopeQuestion,scopedKnowledgeQuestion:q=>q,
 detail:()=>({}),knowledgeAnswerCard:()=>({isConnected:true,replaceChildren(){},setAttribute(){},removeAttribute(){}}),makeElement:()=>({}),
 apiFetch:async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return {ok:true,json:async()=>({})};},renderKnowledgeAnswer:()=>{}};
 vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('async function generateKnowledgeAnswer('),src.indexOf('function decorateKnowledgeView(')),ctx);
 const question='What role do narratives, information gaps and identification play in durable connections between online personalities and followers?';
 await ctx.generateKnowledgeAnswer(question);
 assert.equal(requests.length,1);
 const {url,body}=requests[0];
 assert.equal(url,'/workshops/generate');
 assert.equal(body.situation,question);assert.equal(body.goal,question);
 assert.deepEqual(body.constraints,[]);
 assert.deepEqual(body.source_ids,['creator_a','psychology']);
 assert.deepEqual(body.asset_ids,[]);assert.equal(body.library_id,null);
 assert.equal(body.limit,8);assert.equal(body.output_type,'knowledge_answer');assert.equal(body.save,false);
});


const multiLibraries=[{id:'lib1',name:'Storytelling'},{id:'lib2',name:'Marketing'},{id:'lib3',name:'Unrelated'}];
const multiSources=[{id:'s1',title:'Story 1',library_id:'lib1'},{id:'s2',title:'Marketing 1',library_id:'lib2'},{id:'s3',title:'Other 1',library_id:'lib3'}];
function checkboxByValue(f,id){return f.nodes().find(n=>n.tag==='input'&&n.type==='checkbox'&&n.value===id);}
function searchURLs(f){return f.requests.filter(path=>path.startsWith('/knowledge-assets/search')).map(path=>new URL(path,'http://local'));}
test('selected subset scopes Find, Browse and Create exactly to the chosen libraries',async()=>{
 const f=await viewFixture({library:null,libs:multiLibraries,sources:multiSources});
 const lib1=checkboxByValue(f,'lib1'),lib3=checkboxByValue(f,'lib3');
 lib1.checked=true;lib1.onchange();lib3.checked=true;lib3.onchange();
 assert.deepEqual([...f.main.exploreContext.sourceIds()].sort(),['s1','s3']);
 const selector=f.nodes().find(n=>n.id==='ke-source-scope');
 assert.deepEqual(selector.children.map(option=>option.value),['','s1','s3']);
 const request=f.nodes().find(n=>n.name==='q');request.value='One-on-one facilitation approach';
 await f.nodes().find(n=>n.id==='ke-search-form').submit();
 assert.deepEqual(searchURLs(f).map(url=>url.searchParams.get('library_id')),['lib1','lib3']);
 assert.ok(searchURLs(f).every(url=>!url.searchParams.has('source_id')));
 const browse=f.nodes().find(n=>n.id==='ke-browse');browse.open=true;await browse.ontoggle();
 assert.ok(f.requests.includes('/sources/s1/knowledge-units'));
 assert.ok(f.requests.includes('/sources/s3/knowledge-units'));
 assert.ok(!f.requests.includes('/sources/s2/knowledge-units'));
 const handoff=f.nodes().find(n=>n.textContent==='Use this scope in Create');await handoff.click();
 assert.deepEqual(f.handoffs.at(-1).materials,['s1','s3']);
 assert.equal(f.handoffs.at(-1).library,null);
 assert.ok(f.events.includes('ke-scope-change'));
});

test('selected no-library state fails closed for search and Create, and all restores unrestricted search',async()=>{
 const f=await viewFixture({library:null,libs:multiLibraries,sources:multiSources});
 const chosen=f.nodes().find(n=>n.value==='libraries'&&n.type==='radio');chosen.checked=true;chosen.onchange();
 assert.equal(f.main.exploreContext.sourceIds().length,0);
 const request=f.nodes().find(n=>n.name==='q');request.value='One-on-one facilitation approach';
 await f.nodes().find(n=>n.id==='ke-search-form').submit();
 assert.equal(searchURLs(f).length,0);
 await f.nodes().find(n=>n.textContent==='Use this scope in Create').click();
 assert.equal(f.handoffs.length,0);
 assert.ok(f.notices.some(x=>x.includes('Select at least one library')));
 const all=f.nodes().find(n=>n.value==='all'&&n.type==='radio');all.checked=true;all.onchange();
 assert.deepEqual(f.main.exploreContext.sourceIds(),['s1','s2','s3']);
 await f.nodes().find(n=>n.id==='ke-search-form').submit();
 assert.equal(searchURLs(f).length,1);
 assert.ok(!searchURLs(f)[0].searchParams.has('library_id'));
});

test('a single selected library works and selected material scopes do not widen silently',async()=>{
 const f=await viewFixture({library:'lib2',libs:multiLibraries,sources:multiSources});
 assert.deepEqual(f.main.exploreContext.sourceIds(),['s2']);
 const m=await viewFixture({library:'lib1',libs:multiLibraries,sources:multiSources,materials:['s1']});
 assert.deepEqual(m.main.exploreContext.sourceIds(),['s1']);
 const request=m.nodes().find(n=>n.name==='q');request.value='One-on-one facilitation approach';
 await m.nodes().find(n=>n.id==='ke-search-form').submit();
 assert.equal(searchURLs(m)[0].searchParams.get('source_id'),'s1');
 assert.equal(searchURLs(m)[0].searchParams.get('library_id'),'lib1');
});

test('library scope survives refresh via route hash without converting selected to all',()=>{
 const route={view:'knowledge',library:null,materials:[],source:null,exploreState:{scopeMode:'libraries',libraryIds:['lib1','lib3']}};
 const hash=routeHash(route),parsed=parseRoute(hash);
 assert.deepEqual(parsed.scopeLibraryIds,['lib1','lib3']);
 assert.equal(parsed.scopeMode,'libraries');
 assert.equal(parsed.library,null);
 assert.equal(parseRoute(routeHash({view:'knowledge',exploreState:{scopeMode:'libraries',libraryIds:[]}})).scopeMode,'libraries');
});

test('Ask payload uses exact selected sources and no library-wide fallback',async()=>{
 const f=await viewFixture({library:null,libs:multiLibraries,sources:multiSources});
 for(const id of ['lib1','lib3']){const input=checkboxByValue(f,id);input.checked=true;input.onchange();}
 const src=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
 const requests=[],rendered=[];
 const ctx={answerRevision:0,validateKnowledgeQuestionScope:()=>true,selectedKnowledgeSourceIds:()=>f.main.exploreContext.sourceIds(),beginProcessingStatus:()=>1,endProcessingStatus:()=>{},announceProcessingStatus:()=>{},showKnowledgeScopePrompt:()=>{},
 document:{querySelector:()=>({value:''})},scopeQuestion,scopedKnowledgeQuestion:q=>q,detail:()=>({}),knowledgeAnswerCard:()=>({isConnected:true,replaceChildren(){},setAttribute(){},removeAttribute(){}}),makeElement:()=>({}),
 apiFetch:async(_url,options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>({output:{title:'Grounded answer'}})};},renderKnowledgeAnswer:(...args)=>rendered.push(args)};
 vm.createContext(ctx);vm.runInContext(src.slice(src.indexOf('async function generateKnowledgeAnswer('),src.indexOf('function decorateKnowledgeView(')),ctx);
 await ctx.generateKnowledgeAnswer('What does this source teach?');
 assert.deepEqual([...requests[0].source_ids],['s1','s3']);
 assert.equal(requests[0].library_id,null);assert.equal(requests[0].save,false);
 assert.equal(rendered.length,1);
 for(const id of ['lib1','lib3']){const input=checkboxByValue(f,id);input.checked=false;input.onchange();}
 await ctx.generateKnowledgeAnswer('What does this source teach?');
 assert.equal(requests.length,1);
});


test('empty Find action opens Browse without search requests or AI calls',async()=>{
 const f=await viewFixture();
 const query=f.nodes().find(node=>node.name==='q');
 const form=f.nodes().find(node=>node.id==='ke-search-form');
 const browse=f.nodes().find(node=>node.id==='ke-browse');
 const button=f.nodes().find(node=>node.textContent==='Explore ideas');
 assert.ok(button);
 assert.equal(query.value,'');
 await form.submit();
 assert.equal(browse.open,true);
 assert.ok(f.requests.includes('/sources/s1/knowledge-units'));
 assert.ok(f.requests.every(path=>!path.startsWith('/knowledge-assets/search')));
 assert.equal(f.nodes().filter(node=>node.tag==='h3').length,10);
 query.value='narrative';query.oninput();
 assert.equal(button.textContent,'Find matching ideas');
 query.value='';query.oninput();
 assert.equal(button.textContent,'Explore ideas');
 const enhancements=readFileSync(new URL('../enhancements.js',import.meta.url),'utf8');
 assert.match(enhancements,/request\.required=false;request\.minLength=2;/);
});

test('no selected libraries cannot browse and cannot silently broaden scope',async()=>{
 const f=await viewFixture({library:null,libs:multiLibraries,sources:multiSources});
 const chosen=f.nodes().find(node=>node.value==='libraries'&&node.type==='radio');
 chosen.checked=true;chosen.onchange();
 await f.nodes().find(node=>node.id==='ke-search-form').submit();
 assert.ok(f.notices.some(message=>message.includes('Select at least one library')));
 assert.ok(!f.requests.some(path=>path.includes('/knowledge-units')));
});

test('Browse isolates failed materials, keeps usable results and retries only failures',async()=>{
 const src=[{id:'s1',title:'First',library_id:'lib1'},{id:'s2',title:'Second',library_id:'lib1'},{id:'s3',title:'Third',library_id:'lib1'}];
 const counts=new Map();
 const f=await viewFixture({sources:src,apiImpl:async path=>{
  if(path==='/sources')return {items:src};
  counts.set(path,(counts.get(path)||0)+1);
  if(path.includes('/s2/')&&counts.get(path)===1)throw new Error('intermittent error');
  const id=path.match(/\/sources\/(s\d+)\//)[1];
  return {items:[{canonical_asset:{id,title:'Unit '+id,what_it_says:'Grounded',asset_type:'principle'},support_count:1,evidence_trail:[{source_id:id,evidence:'Test evidence'}]}]};
 }});
 const browse=f.nodes().find(node=>node.id==='ke-browse');browse.open=true;await browse.ontoggle();
 assert.equal(f.nodes().filter(node=>node.tag==='h3').length,2);
 assert.ok(f.nodes().find(node=>node.textContent?.includes('material could not be loaded')));
 const retry=f.nodes().find(node=>node.textContent==='Retry unavailable materials');
 assert.equal(retry.hidden,false);await retry.click();
 assert.equal(f.nodes().filter(node=>node.tag==='h3').length,3);
 assert.equal(retry.hidden,true);
 assert.equal(counts.get('/sources/s1/knowledge-units'),1);
 assert.equal(counts.get('/sources/s2/knowledge-units'),2);
 assert.equal(counts.get('/sources/s3/knowledge-units'),1);
});

test('Browse uses at most four parallel requests for a large selection',async()=>{
 const many=Array.from({length:52},(_,i)=>({id:`s${i}`,library_id:'lib1',title:`Material ${i}`}));
 let active=0,maxActive=0;
 const f=await viewFixture({sources:many,apiImpl:async path=>{
  if(path==='/sources')return {items:many};
  active++;maxActive=Math.max(maxActive,active);
  await new Promise(resolve=>setImmediate(resolve));
  active--;
  return {items:[]};
 }});
 const browse=f.nodes().find(node=>node.id==='ke-browse');browse.open=true;await browse.ontoggle();
 assert.equal(f.requests.filter(path=>path.endsWith('/knowledge-units')).length,52);
 assert.equal(maxActive,4);
 assert.ok(f.nodes().find(node=>node.textContent==='No prepared ideas are available in the selected materials yet.'));
});

test('switching library scope discards stale Browse responses',async()=>{
 const src=multiSources;
 const pending=[];
 const f=await viewFixture({library:null,libs:multiLibraries,sources:src,apiImpl:async path=>{
  if(path==='/sources')return {items:src};
  if(path.includes('/knowledge-units'))return await new Promise(resolve=>pending.push({path,resolve}));
  return {items:[]};
 }});
 const browse=f.nodes().find(node=>node.id==='ke-browse');browse.open=true;
 const load=browse.ontoggle();
 await Promise.resolve();
 const lib1=checkboxByValue(f,'lib1');lib1.checked=true;lib1.onchange();
 for(const item of pending)item.resolve({items:[{canonical_asset:{id:'old',title:'Stale',asset_type:'concept'},support_count:1,evidence_trail:[]}]});
 await load;
 assert.equal(f.nodes().filter(node=>node.tag==='h3').length,0);
 assert.ok(!f.ctx.state.selected.has('old'));
});
