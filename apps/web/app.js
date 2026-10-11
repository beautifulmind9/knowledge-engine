import { revisionPayload } from './output-revision.js';
import {api, apiFetch, csrfToken} from './api.js';
import {createNavigation} from './navigation.js';
import {newInteractionDraft, captureRequest, correctDraft, interpretDraft, draftNeedsInterpretation, workshopRequest, evidenceIdentity, confirmDraft, preparedGenerationRequest} from './interaction-draft.js';
import { PAGE_SIZE, filterUnits, createSearchController } from './knowledge-browser.js';
const main=document.querySelector('main'), feedback=document.querySelector('#feedback');
let interactionDraft=newInteractionDraft(),createMaterials=null,viewRevision=0;
function beginView(){const revision=++viewRevision;return ()=>revision===viewRevision;}
let homeDraft=newInteractionDraft(),exploreState=null,explorePicker=false;
function captureDraft(){main.querySelector('#create-brief')?.captureInteraction();main.captureExplore?.();}
function freshExplore(query=''){return {query,chapter:'',idea:'',contextOpen:false,contextMode:'both',promptMode:null,type:'',section:'',visible:PAGE_SIZE,browseOpen:false,results:null,answer:null};}
function draftMeaningful(){return !!interactionDraft.originalRequest.trim()||Object.values(interactionDraft.values).some(v=>v.provenance==='user-corrected'&&v.value?.length)||interactionDraft.scope.value.assetIds.length>0;}
async function openCreate(handoff=null){
 captureDraft();
 if(!handoff)return navigate('workshop',{library:interactionDraft.scope.value.libraryId,materials:interactionDraft.scope.value.sourceIds,selectedIds:interactionDraft.scope.value.assetIds});
 const apply=()=>{let draft=newInteractionDraft(handoff.request||'');if(handoff.outputType)draft=correctDraft(draft,'output_type',handoff.outputType);draft=correctDraft(draft,'scope',{libraryId:handoff.library||null,sourceIds:handoff.materials||[],assetIds:handoff.selectedIds||[]});return navigate('workshop',{library:handoff.library||null,materials:handoff.materials||[],selectedIds:handoff.selectedIds||[],newDraft:draft});};
 if(!draftMeaningful())return apply();
 main.querySelector('#create-handoff')?.remove();
 const choice=card('You already have a Create draft','Use the new request and its selected knowledge, or keep your current draft.');choice.id='create-handoff';choice.setAttribute('role','region');choice.setAttribute('aria-label','Choose which Create draft to use');
 const visibleRequest=main.querySelector('[name=home_request]')||main.querySelector('[name=q]');
 if(handoff.request&&visibleRequest?.value!==handoff.request)choice.append(el('p',handoff.request,'handoff-request'));
 choice.append(actions(button('Use new request',apply,'primary'),button('Keep current draft',()=>openCreate())));main.insertBefore(choice,main.children[3]);choice.setAttribute('tabindex','-1');choice.focus();
}
const state={library:null,source:null,selected:new Set(),view:'home'};
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
function message(text,error=false){feedback.textContent=text;feedback.className=error?'error':'';}
function button(text,action,cls=''){const b=el('button',text,cls);b.type='button';b.onclick=()=>run(action,b);return b;}
async function run(fn,b){if(b)b.disabled=true;main.setAttribute('aria-busy','true');message('Working…');let revision=viewRevision;try{const pending=fn();revision=viewRevision;await pending;if(revision!==viewRevision)return;if(feedback.textContent==='Working…')message('');}catch(e){if(revision===viewRevision)message(e.message,true);}finally{if(b)b.disabled=false;if(revision===viewRevision)main.removeAttribute('aria-busy');}}
function field(label,name,kind='input',value=''){const l=el('label',label),i=el(kind);i.name=name;if(kind==='textarea')i.rows=4;i.value=value;l.append(i);return [l,i];}
function select(label,values,current='',multiple=false){const [l,s]=field(label,label,'select');s.multiple=multiple;for(const [id,name] of values){const o=el('option',name);o.value=id;o.selected=Array.isArray(current)?current.includes(id):id===current;s.append(o);}return [l,s];}
function form(onSubmit){const f=el('form');f.onsubmit=e=>{e.preventDefault();return run(()=>onSubmit(new FormData(f)),f.querySelector('[type=submit]'));};return f;}
function submit(text){const b=el('button',text,'primary');b.type='submit';return b;}
function heading(kicker,title,description){main.captureExplore=null;main.exploreContext=null;const signout=main.querySelector('#beta-logout');if(signout){signout.hidden=true;document.body.append(signout);}main.replaceChildren(el('div',kicker,'kicker'),el('h1',title),el('p',description,'intro'));}
function card(title,description){const c=el('section',undefined,'card');c.append(el('h3',title));if(description)c.append(el('p',description));return c;}
function actions(...buttons){const d=el('div',undefined,'actions');d.append(...buttons);return d;}
function detail(title,...nodes){const d=el('details');d.append(el('summary',title),...nodes);return d;}
function list(items){const u=el('ul');for(const item of items)u.append(el('li',item));return u;}
async function navigate(view,options={}){
 captureDraft();
 if(view==='workshop'&&!('materials' in options)&&!('selectedIds' in options))return openCreate();
 const pending=router.go({view,library:state.library,materials:createMaterials??(state.source?[state.source]:[]),source:state.source,...(view==='knowledge'?{exploreState:freshExplore(),picker:false,selectedIds:[]}:{}),...options},options.replace),revision=viewRevision;
 await pending;return revision===viewRevision;
}
function replaceScope(view){router.go({view,library:state.library,materials:createMaterials||[],source:state.source,selectedIds:[...state.selected],...(view==='knowledge'?{exploreState,picker:explorePicker}:{})},true,false);}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=e=>{e.preventDefault();return run(()=>navigate(b.dataset.view),b);});
async function libraries(){const data=await api('/libraries');return data.items;}
async function sourceItems(){return (await api('/sources'+(state.library?'?library_id='+encodeURIComponent(state.library):''))).items;}
function readiness(source){if(source.stopped_reason||/failed|not_supported/.test(source.processing_status))return 'Needs attention';return source.processing_status==='knowledge_interpreted'?'Ready to use':source.chunks_path?'Preparing':'Not prepared';}
async function homeView(){beginView();heading('HOME','What would you like to do?','What are you trying to learn, decide, make, plan or figure out?');
 const entry=el('section',undefined,'home-intent'),[label,input]=field('Your request','home_request','textarea',homeDraft.originalRequest);input.rows=3;input.placeholder='Start with what’s on your mind.';
 input.oninput=()=>{main.querySelector('#create-handoff')?.remove();homeDraft=captureRequest(homeDraft,input.value);};
 entry.append(label,actions(button('Ask & Explore',()=>navigate('knowledge',{library:null,materials:[],source:null,exploreState:freshExplore(input.value)})),button('Create something',()=>input.value.trim()?openCreate({request:input.value,materials:[],selectedIds:[]}):openCreate())),el('p','Choose what you’d like to do with your request.','muted'));main.append(entry);
 const choices=el('div',undefined,'home-choices');for(const [title,description,view] of [['Add to my library','Bring in material you want to use.','library'],['Continue my work','Return to something created earlier.','outputs']]){const row=el('section');row.append(button(title,()=>navigate(view,view==='library'?{add:true}:{})),el('p',description));choices.append(row);}main.append(choices);}
async function libraryView(_id,route={}){const active=beginView();heading('LIBRARY','Your library','Add material, find useful ideas, and bring them into your work.');const libs=await libraries();if(!active())return;const [l,s]=select('Current library',[['','All libraries'],...libs.map(l=>[l.id,l.name])],state.library||'');s.onchange=()=>{state.library=s.value||null;state.source=null;state.selected.clear();run(()=>navigate('library',{replace:true}));};main.append(l,actions(button('Ask & Explore',()=>navigate('knowledge',{materials:[],source:null}),'primary')));
 const create=form(async fd=>{const lib=await api('/libraries',{method:'POST',body:{name:fd.get('name'),description:fd.get('description')}});if(!active())return;state.library=lib.id;if(!await navigate('library',{add:true,replace:true}))return;message('Library created.');});for(const [label,name] of [['Library name','name'],['Description','description']]){const [l,i]=field(label,name);i.required=name==='name';create.append(l);}create.append(submit('Create library'));const createDetails=detail('Create a library',create);createDetails.open=!libs.length;main.append(createDetails);if(!libs.length){main.append(el('p','Create your first library above, then add material.','empty'));return;}
 const sources=await sourceItems();if(!active())return;const grid=el('div',undefined,'grid');for(const s of sources){const c=card(s.title,s.author||'Your material');c.append(el('span',readiness(s),'badge'),actions(button('Open material',()=>navigate('material',{id:s.id}))));grid.append(c);}main.append(grid);if(!sources.length)main.append(el('p','No materials yet. Add a file to begin.','empty'));
 const add=form(async fd=>{const file=fd.get('file');if(!file||file.size===0)throw Error('The uploaded file is empty.');const source=await api('/sources',{method:'POST',body:{library_id:fd.get('Library'),title:fd.get('title'),author:fd.get('author'),source_type:'document'}});try{const upload=new FormData();upload.append('file',file);await api(`/sources/${source.id}/upload`,{method:'POST',body:upload});}catch(e){if(!active())return;await navigate('material',{id:source.id,library:fd.get('Library')});throw e;}if(!active())return;if(!await navigate('material',{id:source.id,library:fd.get('Library')}))return;message('Material added. Prepare it to find useful ideas.');});const c=card('Add material','PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON · up to 25 MB');const [ll,ss]=select('Library',libs.map(l=>[l.id,l.name]),state.library||libs[0]?.id);ss.required=true;add.append(ll);for(const [label,name] of [['Title','title'],['Author / creator','author'],['Material file','file']]){const [l,i]=field(label,name);i.required=name!=='author';if(name==='file'){i.type='file';i.accept='.pdf,.epub,.docx,.txt,.md,.html,.htm,.csv,.json';}add.append(l);}add.append(submit('Add material'));c.append(add);const addDetails=detail('Add material',c);addDetails.open=route.add||!sources.length;main.insertBefore(addDetails,grid);}
async function sourceView(id){const active=beginView();state.source=id;heading('LIBRARY','Opening material…','');const [source,summary]=await Promise.all([api(`/sources/${id}`),api(`/sources/${id}/summary`)]);if(!active())return;const readinessLabels={added:'Added',ready_to_build:'Ready to build knowledge',partly_ready:'Partly ready',ready:'Ready',unknown:'Readiness unknown'};heading(readinessLabels[summary.readiness],source.title,source.author||'Prepare this material to find ideas you can use.');if(summary.attention_message)main.append(el('p',summary.attention_message,'muted'));else if(summary.operation==='build_unconfirmed')main.append(el('p','Previous build has not reported completion.','muted'));main.append(actions(button('← Library',()=>navigate('library')),...(!source.chunks_path&&source.file_path?[button('Prepare material',async()=>{message('Reading source…');await api(`/sources/${id}/process`,{method:'POST'});if(!active())return;if(!await navigate('material',{id,replace:true}))return;message('Text is ready. Continue preparing to find useful ideas.');},'primary')]:[])));
 if(!source.file_path){const upload=form(async fd=>{const data=new FormData();data.append('file',fd.get('file'));await api(`/sources/${id}/upload`,{method:'POST',body:data});if(!active())return;await navigate('material',{id,replace:true});});const [l,i]=field('Upload material file','file');i.type='file';i.required=true;upload.append(l,submit('Upload'));main.append(upload);}
 if(source.chunks_path){const c=card('Preparation',summary.coverage_text||'Coverage is unavailable.');const progress=el('progress');progress.max=summary.total_parts||1;progress.value=summary.completed_parts||0;progress.setAttribute('aria-label','Preparation progress');progress.hidden=summary.total_parts===null;c.append(progress);const complete=summary.readiness==='ready';const interpretationActions=[];if(complete)c.append(el('p','All current parts are ready.','muted'));else if(summary.next_action==='build_knowledge'||summary.next_action==='continue_building')interpretationActions.push(button('Continue preparing',async()=>{message('Building knowledge…');const r=await api(`/sources/${id}/interpret?max_chunks=1`,{method:'POST'});if(!active())return;if(!await navigate('material',{id,replace:true}))return;message(r.stopped_reason?'Preparation paused. Check Advanced details for recovery options.':`${r.processed_this_run} section prepared.`,!!r.stopped_reason);},'primary'));interpretationActions.push(button('Browse useful ideas',()=>navigate('knowledge',{source:id,materials:[id],library:source.library_id||null})));c.append(actions(...interpretationActions));main.append(c);const ideas=await api(`/sources/${id}/knowledge-units`).catch(()=>({items:[],unavailable:true}));if(!active())return;if(ideas.unavailable)main.append(el('p','Available ideas could not be loaded. You can still open Browse useful ideas.','muted'));if(ideas.items.length)main.append(el('h2','Useful ideas found'),list(ideas.items.slice(0,5).map(g=>`${g.canonical_asset.title}: ${g.canonical_asset.what_it_says}`)));main.append(button('Create using this material',()=>{return openCreate({request:'',materials:[id],library:source.library_id||null,selectedIds:[]});},complete?'primary':''));
 const advanced=detail('Advanced details');main.append(advanced);let diagnosticsLoaded=false,diagnosticsLoading=false;
 advanced.ontoggle=()=>{if(!advanced.open||diagnosticsLoaded||diagnosticsLoading)return;diagnosticsLoading=true;return run(async()=>{try{const [audit,chunks]=await Promise.all([api(`/sources/${id}/audit`),api(`/sources/${id}/chunks`)]);if(!active())return;
 const auditCard=card('Quality & recovery',`Overlap: ${Math.round(audit.overlap_rate*100)}% · Superseded: ${audit.superseded_assets.length} · Old schema: ${audit.old_schema_assets.length}`);auditCard.append(list([`Active assets: ${audit.asset_count}`,`Consolidated units: ${audit.knowledge_unit_count}`,`Missing evidence: ${audit.missing_evidence.length}`,`Missing keywords: ${audit.missing_keywords.length}`,`Evidence needing human review: ${audit.evidence_needing_review.length}`,`Asset types: ${Object.entries(audit.asset_types).map(([k,v])=>`${k} ${v}`).join(', ')||'None yet'}`,`Confidence scores: ${Object.entries(audit.confidence_distribution).map(([k,v])=>`${k}/5: ${v}`).join(', ')||'None yet'}`]),el('p',audit.note,'muted'));const latestByChunk=new Map();for(const job of audit.jobs)latestByChunk.set(job.chunk_id,job);const recoverable=[...latestByChunk.values()].filter(j=>summary.recovery.some(r=>r.job_id===j.id));if(recoverable.length){for(const job of recoverable){const reset=button('Recover job',async()=>{await api(`/knowledge-extractions/${job.id}/recover`,{method:'POST'});if(!active())return;await navigate('material',{id,replace:true});});reset.disabled=!summary.recovery.find(r=>r.job_id===job.id).allowed;auditCard.append(el('p',`${job.chunk_id}: ${job.status} — ${job.error||'Processing'}`),reset);}}else auditCard.append(el('p','No current failed or stale-running extraction jobs. Earlier failed attempts remain in history but do not need recovery.','muted'));advanced.append(detail('Audit and recovery',auditCard));
 const manual=form(async fd=>{const chunkId=fd.get('Chunk');const job=(await api('/knowledge-extractions',{method:'POST',body:{source_id:id,chunk_id:chunkId,reprocess:fd.get('replace')==='on'}})).job;const raw=fd.get('result').trim();if(raw){let parsed;try{parsed=JSON.parse(raw);}catch{throw new Error('Paste valid extraction JSON with an assets array.');}await api(`/knowledge-extractions/${job.id}/results`,{method:'POST',body:parsed});if(!active())return;if(!await navigate('material',{id,replace:true}))return;message('Knowledge imported and validated.');}else{const req=await api(`/knowledge-extractions/${job.id}/request`);download(`${job.id}-prompt.json`,JSON.stringify(req,null,2),'application/json');message('Extraction prompt downloaded. Return here to import the structured result.');}});const [cl,cs]=select('Chunk',chunks.items.map(c=>[c.id,`Chunk ${c.chunk_index} · ${c.word_count} words${c.chapter_or_section?' · '+c.chapter_or_section:''}`]));manual.append(cl);const [rl,ri]=field('Structured extraction result (leave empty to download prompt)','result','textarea');manual.append(rl);const [pl,pi]=field('Intentionally replace this chunk’s active knowledge','replace');pi.type='checkbox';pl.className='check';manual.append(pl,submit('Download prompt / import result'));advanced.append(detail('Manual extraction or intentional reprocessing',el('p','Use your own structured response without an API call. Existing active knowledge is replaced only after validation succeeds.','muted'),manual));
 diagnosticsLoaded=true;}catch(error){if(active())message('Advanced details could not be loaded. Available knowledge and readiness are unchanged.',true);}finally{diagnosticsLoading=false;}});};
 }
 main.append(detail('Advanced details — delete material',actions(button('Delete material and related work',async()=>{if(!confirm('Delete this material, its file, all its ideas, and every saved work history using those ideas? This cannot be undone.'))return;await api(`/sources/${id}?delete_outputs=true`,{method:'DELETE'});if(!active())return;state.selected.clear();state.source=null;if(!await navigate('library',{replace:true}))return;message('Material and related work deleted.');},'danger'))));}
function download(name,text,type='text/plain'){const a=el('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function knowledgeView(){const active=beginView();
 heading('LIBRARY / ASK & EXPLORE','Ideas you can put to work.',explorePicker?'Choose ideas for your Create draft, or explore your materials.':'Find useful ideas or ask a grounded question about your materials.');
 exploreState ||= freshExplore();const local=exploreState;main.exploreContext={state:local,sourceIds:()=>s.value?[s.value]:sources.map(item=>item.id),handoff:(request,sourceIds)=>openCreate({request,materials:sourceIds,library:state.library,selectedIds:[...state.selected],outputType:'knowledge_answer'})};
 const [sourceList,scopeLibraries]=await Promise.all([sourceItems(),libraries()]);if(!active())return;
 let sources=sourceList;
 if(createMaterials?.length)sources=sources.filter(source=>createMaterials.includes(source.id));
 if(!sources.some(source=>source.id===state.source))state.source=null;
 const broadScope=createMaterials?.length?sources.map(source=>source.title).join(', '):state.library?scopeLibraries.find(l=>l.id===state.library)?.name||'Current library':'Across your library';
 const [l,s]=select('Search scope',[['',broadScope],...sources.map(source=>[source.id,source.title])],state.source||'');
 s.id='ke-source-scope';
 const [ql,qi]=field('What are you looking for or wondering about?','q','textarea',local.query);
 qi.placeholder='e.g. One-on-one facilitation approach';
 const search=form(async()=>{if(qi.value.trim().length<2){controller.invalidate();message('Enter at least two characters to search.');return;}browse.open=false;await controller.search(qi.value.trim(),s.value);});
 search.id='ke-search-form';qi.id='explore-request';qi.rows=3;const captureActions=actions(submit('Find ideas'));captureActions.id='explore-actions';search.append(l,ql,captureActions);main.append(search);
 const searchPanel=el('section');searchPanel.hidden=true;searchPanel.id='ke-search-results';searchPanel.setAttribute('aria-live','polite');
 const selectedCount=el('p',undefined,'muted');
 const handoffButton=button('',()=>explorePicker?navigate('workshop',{selectedIds:[...state.selected]}):openCreate({request:local.query,library:state.library,materials:s.value?[s.value]:createMaterials||[],selectedIds:[...state.selected]}),'primary');
 const updateSelection=()=>{selectedCount.textContent=`${state.selected.size} ideas selected for Create`;handoffButton.textContent=state.selected.size?'Use selected ideas in Create':'Use this scope in Create';};updateSelection();
 main.append(searchPanel,actions(handoffButton,selectedCount));
 const browse=detail('Browse useful ideas');browse.id='ke-browse';
 browse.append(el('p','Explore ideas from the materials above.','muted'));
 const filters=el('div',undefined,'form-grid');
 const [tl,type]=select('Idea type',[['','All types']]);
 const [cl,chapter]=select('Chapter / section',[['','All chapters / sections']]);filters.append(tl,cl);
 const browseStatus=el('p',undefined,'muted'),inventory=el('div',undefined,'grid');
 let items=[],loaded=false,loading=false,visible=local.visible,browseRevision=0;
 const more=button('Show more',()=>{visible+=PAGE_SIZE;renderBrowse();});
 browse.append(filters,browseStatus,inventory,more);main.append(browse);more.hidden=true;
 function cards(target,groups){target.replaceChildren();for(const g of groups){const a=g.canonical_asset,c=card(a.title,a.what_it_says);c.append(el('span',`${a.asset_type.replaceAll('_',' ')} · ${g.support_count} supporting references`,'badge'));
 const [label,check]=field('Use in Create',a.id);check.type='checkbox';check.checked=state.selected.has(a.id);label.className='check';check.onchange=()=>{main.querySelector('#create-handoff')?.remove();if(check.checked)state.selected.add(a.id);else state.selected.delete(a.id);updateSelection();for(const other of main.querySelectorAll('input[type=checkbox]'))if(other.name===a.id)other.checked=check.checked;};c.append(label);
 c.append(detail('Source & evidence',...(g.evidence_trail||[]).map(e=>el('p',`${sources.find(source=>source.id===e.source_id)?.title||'Material'}${e.chapter_or_section?' · '+e.chapter_or_section:''}\n${e.evidence}`,'evidence'))));c.append(button('Ask about this idea',()=>main.exploreContext.configureIdea?.(a.title)));target.append(c);}}
 const controller=createSearchController(async(query,scope)=>{const q=new URLSearchParams({q:query,consolidated:'true',limit:'50'});if(state.library)q.set('library_id',state.library);const scoped=scope?[scope]:createMaterials?.length?sources.map(source=>source.id):[null];const batches=await Promise.all(scoped.map(id=>{const params=new URLSearchParams(q);if(id)params.set('source_id',id);return api('/knowledge-assets/search?'+params);}));return [...new Map(batches.flatMap(batch=>batch.items).map(group=>[group.canonical_asset.id,group])).values()].slice(0,50);},(groups,status,query)=>{
 if(!active())return;if(status==='results')local.results={groups,query};searchPanel.hidden=status==='idle';searchPanel.replaceChildren();if(status==='idle')return;
 searchPanel.append(el('h2',status==='loading'?'Searching…':status==='error'?'Search could not be completed':`Search results for “${query}”`));
 if(status==='results'){searchPanel.append(el('p',groups.length?`${groups.length} matches (up to 50). Narrow the query for more specific results.`:'No matching ideas. Try different terms or browse useful ideas.','muted'));const grid=el('div',undefined,'grid');cards(grid,groups);searchPanel.append(grid);}});
 function renderBrowse(){const filtered=filterUnits(items,type.value,chapter.value);cards(inventory,filtered.slice(0,visible));browseStatus.textContent=`Browsing ${Math.min(visible,filtered.length)} of ${filtered.length} ideas`;more.hidden=visible>=filtered.length;}
 async function loadBrowse(){if(loaded||loading)return;loading=true;const ticket=++browseRevision;browseStatus.textContent='Loading inventory…';try{const scoped=s.value?sources.filter(source=>source.id===s.value):sources;const batches=await Promise.all(scoped.map(source=>api(`/sources/${source.id}/knowledge-units`)));if(!active()||ticket!==browseRevision)return;items=batches.flatMap(batch=>batch.items);loaded=true;
 type.replaceChildren(new Option('All types',''),...[...new Set(items.map(g=>g.canonical_asset.asset_type))].sort().map(value=>new Option(value.replaceAll('_',' '),value)));
 const chapters=[...new Set(items.flatMap(g=>[g.canonical_asset.chapter_or_section,...(g.evidence_trail||[]).map(e=>e.chapter_or_section)]).filter(Boolean))].sort();chapter.replaceChildren(new Option('All chapters / sections',''),...chapters.map(value=>new Option(value,value)));type.value=local.type;chapter.value=local.section;renderBrowse();}catch(error){if(active()&&ticket===browseRevision){browseStatus.textContent='Inventory could not be loaded. Close and reopen Browse to retry.';throw error;}}finally{if(ticket===browseRevision)loading=false;}}
 browse.ontoggle=()=>{if(browse.open)return run(loadBrowse);};
 type.onchange=chapter.onchange=()=>{visible=PAGE_SIZE;renderBrowse();};
 qi.oninput=()=>{main.querySelector('#create-handoff')?.remove();local.query=qi.value;local.results=null;controller.invalidate();browse.open=false;};
 s.onchange=()=>{main.querySelector('#create-handoff')?.remove();state.source=s.value||null;state.selected.clear();updateSelection();controller.invalidate();browseRevision++;loaded=false;loading=false;items=[];visible=PAGE_SIZE;inventory.replaceChildren();more.hidden=true;browseStatus.textContent='';browse.open=false;type.replaceChildren(new Option('All types',''));chapter.replaceChildren(new Option('All chapters / sections',''));local.results=null;local.answer=null;local.browseOpen=false;local.type='';local.section='';local.visible=PAGE_SIZE;replaceScope('knowledge');document.dispatchEvent(new Event('ke-scope-change'));};
 main.captureExplore=()=>{local.query=qi.value;local.type=type.value;local.section=chapter.value;local.visible=visible;local.browseOpen=browse.open;local.selectedIds=[...state.selected];};
 // Restore deterministic search/filter state, without repeating any AI action.
 if(local.results){const grid=el('div',undefined,'grid');searchPanel.hidden=false;searchPanel.append(el('h2',`Search results for “${local.results.query}”`),grid);cards(grid,local.results.groups);}
 if(local.browseOpen){browse.open=true;await loadBrowse();}
 if(active())document.dispatchEvent(new Event('ke-explore-ready'));
}
async function workshopView(){
 const active=beginView();
 heading('CREATE','What are you working on?','Tell us what you want to make. We’ll organize your request and find relevant knowledge.');
 const [sourceData,mods,libs]=await Promise.all([api('/sources'),api('/outputs/modes'),libraries()]);
 if(!active())return;
 const catalog=()=>({sources:sourceData.items,modes:mods.items,libraries:libs,selectedAssetIds:[...state.selected]});
 const routeScope={libraryId:state.library,sourceIds:createMaterials??(state.source?[state.source]:[]),assetIds:[...state.selected]};
 if(JSON.stringify(interactionDraft.scope.value)!==JSON.stringify(routeScope))interactionDraft=correctDraft(interactionDraft,'scope',routeScope);
 let actionRevision=0,controls=new Map(),scopeControls=null;
 const container=el('section',undefined,'card'),understanding=el('section',undefined,'understanding'),preview=el('section',undefined,'knowledge-preview');
 preview.setAttribute('aria-live','polite');
 const [requestLabel,request]=field('What would you like to make, decide, plan or figure out?','original_request','textarea',interactionDraft.originalRequest);
 request.placeholder='Tell Knowledge Engine as much or as little as you know.';request.rows=5;request.required=true;request.minLength=2;
 const original=detail('Your original request · Edit',requestLabel);original.open=true;original.children[0].hidden=true;
 const f=el('form');f.id='create-brief';f.onsubmit=event=>event.preventDefault();f.captureInteraction=sync;
 const create=button('Create',async()=>{
   if(!f.reportValidity())return;
   sync();
   const payload=preparedGenerationRequest(interactionDraft,catalog());
   const brief=workshopRequest(interactionDraft,catalog());
   interactionDraft=confirmDraft(interactionDraft,brief);
   const identity=evidenceIdentity(interactionDraft,brief),ticket=++actionRevision;
   let r;try{r=await api('/workshops/generate',{method:'POST',body:payload});}catch(error){
     if(!active()||ticket!==actionRevision)return;
     interactionDraft={...interactionDraft,prepared:null,confirmation:{state:'unconfirmed',snapshot:null}};
     showStale('Knowledge needs an update before another Create attempt.');throw error;
   }
   if(!active()||ticket!==actionRevision||identity!==evidenceIdentity(interactionDraft,workshopRequest(interactionDraft,catalog())))return;
   if(!await navigate('work',{id:r.saved_output.id}))return;
   message(r.quality_report?.validation_status==='failed'?'Saved as a draft with timing errors. Review before use.':r.quality_report?.validation_status==='needs_review'?'Saved as a draft. Some checks need review.':'Generated and saved as version 1. Human review is still required.');
 },'primary');
 const providerNote=el('p','Uses the knowledge shown above.','muted');
 const finalAction=el('div',undefined,'create-final');finalAction.append(create,providerNote);finalAction.hidden=true;
 const update=button('Update knowledge',prepare);update.hidden=true;
 const next=button('Continue',async()=>{
   sync();interactionDraft=interpretDraft(interactionDraft,catalog());
   state.library=interactionDraft.scope.value.libraryId;createMaterials=[...interactionDraft.scope.value.sourceIds];state.source=createMaterials.length===1?createMaterials[0]:null;
   state.selected=new Set(interactionDraft.scope.value.assetIds);replaceScope('workshop');
   original.open=false;original.children[0].hidden=false;next.hidden=true;renderUnderstanding();
   if(interactionDraft.clarification.state==='needed'){preview.replaceChildren();update.hidden=true;return;}
   await prepare();
 },'primary');
 function showStale(text='Knowledge needs an update for your changes.'){
   preview.replaceChildren(el('p',text,'muted'));create.disabled=true;finalAction.hidden=true;
   update.hidden=draftNeedsInterpretation(interactionDraft)||interactionDraft.clarification.state==='needed';
 }
 function invalidateView(){actionRevision++;showStale();}
 function sync(){
   let nextDraft=captureRequest(interactionDraft,request.value);
   for(const [name,input] of controls){
     const old=nextDraft.values[name].value,value=Array.isArray(old)?input.value.split('\n').map(s=>s.trim()).filter(Boolean):input.value;
     if(JSON.stringify(old)!==JSON.stringify(value))nextDraft=correctDraft(nextDraft,name,value);
   }
   if(JSON.stringify([...state.selected])!==JSON.stringify(nextDraft.scope.value.assetIds))nextDraft=correctDraft(nextDraft,'scope',{...nextDraft.scope.value,assetIds:[...state.selected]});
   if(nextDraft!==interactionDraft){interactionDraft=nextDraft;invalidateView();}
   state.library=interactionDraft.scope.value.libraryId;createMaterials=[...interactionDraft.scope.value.sourceIds];state.source=createMaterials.length===1?createMaterials[0]:null;
 }
 request.oninput=()=>{sync();understanding.hidden=true;preview.replaceChildren();finalAction.hidden=true;update.hidden=true;next.hidden=false;};
 f.seedInteraction=(question,sourceIds)=>{
   if(sourceIds.some(id=>!sourceData.items.some(s=>s.id===id)))throw Error('Choose the materials again from your library.');
   return openCreate({request:question,materials:sourceIds,selectedIds:[],outputType:'knowledge_answer'});
 };
 function commit(rebuild=false){
   sync();
   if(draftNeedsInterpretation(interactionDraft))return;
   if(rebuild)renderUnderstanding();else renderIntent();
   if(interactionDraft.clarification.state!=='needed')return run(prepare);
 }
 function renderUnderstanding(){
   const adjustOpen=!!understanding.querySelector('#create-adjustments')?.open,scopeOpen=!!understanding.querySelector('#create-scope')?.open;
   controls=new Map();scopeControls=null;understanding.replaceChildren(el('h2','Here’s what I understood'));
   understanding.hidden=false;
   const v=interactionDraft.values;
   understanding.append(el('p',v.task.value,'intent-summary'),el('div',undefined,'intent-details'));renderIntent();
   const adjustments=detail('Adjust details');adjustments.id='create-adjustments';adjustments.open=adjustOpen;
   const labels=[['Task','task'],['Goal','goal'],['Audience','audience'],['Tone / style','tone_or_style'],['Context','situation'],['About you or this project','creator_context'],['Important constraints','constraints'],['Direction','creative_intent'],['Preserve','preserve'],['Avoid','avoid']];
   const hiddenFields=[];
   for(const [label,name] of labels){
     const item=v[name],value=Array.isArray(item.value)?item.value.join('\n'):item.value;
     const [l,input]=field(label,name,Array.isArray(item.value)||['situation','goal'].includes(name)?'textarea':'input',value);
     controls.set(name,input);input.oninput=sync;input.onchange=()=>commit();
     l.hidden=(!value&&item.provenance!=='user-corrected')||(['situation','goal'].includes(name)&&item.provenance!=='user-corrected');
     if(l.hidden)hiddenFields.push([name,label,l]);
     adjustments.append(l);
   }
   const [addLabel,add]=select('Add a detail',[['','Choose if useful'],...hiddenFields.map(([name,label])=>[name,label])]);
   add.onchange=()=>{const item=hiddenFields.find(([name])=>name===add.value);if(item){item[2].hidden=false;controls.get(item[0]).focus();}};
   adjustments.append(addLabel);
   const [ml,mode]=select('Result',[['','Choose a result'],...mods.items.map(m=>[m.id,m.label])],v.output_type.value);
   mode.name='output_type';controls.set('output_type',mode);
   const result=detail('Result · '+(mods.items.find(m=>m.id===mode.value)?.label||'Needs your input')+(v.output_format.value?' · '+v.output_format.value:''),ml);
   if(!mode.value){result.open=true;result.append(el('p','What would you like to make? Choose a result to continue.','muted'));}
   mode.onchange=()=>{sync();controls.delete('output_format');interactionDraft=correctDraft(interactionDraft,'output_format','');const pending=commit(true);controls.get('output_type').focus();return pending;};
   const formats=mods.items.find(m=>m.id===mode.value)?.formats||[];
   if(formats.length){const [fl,format]=select('Format',[['','No specific format'],...formats.map(x=>[x,x])],v.output_format.value);format.name='output_format';controls.set('output_format',format);format.onchange=()=>{sync();const pending=commit(true);controls.get('output_format').focus();return pending;};result.append(fl);}
   // A recognized format is already apparent in the summary; keep its control in Adjust details.
   if(mode.value&&v.output_type.provenance!=='user-corrected'&&v.output_format.provenance!=='user-corrected')adjustments.append(result);else understanding.append(result);
   const scopeValue=interactionDraft.scope.value;
   const scopeText=interactionDraft.scope.resolution==='ambiguous'?'Needs your input':scopeValue.sourceIds.length?sourceData.items.filter(s=>scopeValue.sourceIds.includes(s.id)).map(s=>s.title).join(', '):scopeValue.libraryId?libs.find(l=>l.id===scopeValue.libraryId)?.name:'Across your library';
   const scope=detail('Search scope · '+scopeText);scope.id='create-scope';scope.open=scopeOpen;
   scope.append(el('p','Find relevant prepared knowledge in this scope. Documents and sections that have not been prepared do not contribute.','muted'));
   const [ll,lib]=select('Library scope',[['','Across your library'],...libs.map(l=>[l.id,l.name])],scopeValue.libraryId||'');
   const choices=el('fieldset');choices.append(el('legend','Materials'));
   const checks=[];
   for(const source of sourceData.items){
     const [l,input]=field(source.title,'material_'+source.id);input.type='checkbox';input.value=source.id;input.checked=scopeValue.sourceIds.includes(source.id);l.className='check';
     l.hidden=!!lib.value&&source.library_id!==lib.value;input.disabled=l.hidden;checks.push(input);choices.append(l);input.onchange=scopeChanged;
   }
   scopeControls={lib,checks};
   function scopeChanged(){
     state.selected.clear();
     for(const input of checks){const show=!lib.value||sourceData.items.find(s=>s.id===input.value)?.library_id===lib.value;input.disabled=!show;input.closest('label').hidden=!show;if(!show)input.checked=false;}
     interactionDraft=correctDraft(interactionDraft,'scope',{libraryId:lib.value||null,sourceIds:checks.filter(c=>c.checked&&!c.disabled).map(c=>c.value),assetIds:[]});
     state.library=lib.value||null;createMaterials=[...interactionDraft.scope.value.sourceIds];state.source=createMaterials.length===1?createMaterials[0]:null;replaceScope('workshop');invalidateView();
     const current=interactionDraft.scope.value;scope.children[0].textContent='Search scope · '+(current.sourceIds.length?sourceData.items.filter(s=>current.sourceIds.includes(s.id)).map(s=>s.title).join(', '):current.libraryId?libs.find(l=>l.id===current.libraryId)?.name:'Across your library');
     note.textContent='Relevant ideas are found automatically.';clarification.replaceChildren();sync();
     if(interactionDraft.clarification.state!=='needed')return run(prepare);
   }
   lib.onchange=scopeChanged;
   scope.append(ll,choices,el('p','With no materials selected, search the scope above.','muted'));
   const note=el('p',state.selected.size?`${state.selected.size} ideas selected.`:'Relevant ideas are found automatically.','muted');
   scope.append(note,actions(button('Choose ideas myself',()=>{sync();return navigate('knowledge',{picker:true,exploreState:freshExplore(),selectedIds:[...state.selected]});}),button('Clear idea selection',()=>{state.selected.clear();note.textContent='Relevant ideas are found automatically.';sync();return commit();})));
   const clarification=el('div',undefined,'clarification');
   for(const item of interactionDraft.clarification.items.filter(i=>i.field==='scope'))clarification.append(el('p','Needs your input — '+item.message),button('Search across your library',()=>{lib.value='';for(const c of checks)c.checked=false;return scopeChanged();}));
   if(interactionDraft.scope.resolution==='ambiguous')scope.open=true;
   scope.append(clarification);understanding.append(scope,adjustments);
 }
 function renderIntent(){
   const v=interactionDraft.values,summary=understanding.querySelector('.intent-summary'),details=understanding.querySelector('.intent-details');
   if(!summary||!details)return;
   summary.textContent=v.task.value;details.replaceChildren();
   const taskPrefix=String(v.task.value).replace(/[.!?;]+$/,'');
   const extraConstraints=v.constraints.value.filter(s=>!s.startsWith(taskPrefix));
   for(const [label,value] of [['Important constraints',extraConstraints],['Direction',v.creative_intent.value],['Preserve',v.preserve.value],['Avoid',v.avoid.value]]){
     if(value?.length)details.append(el('p',label+': '+(Array.isArray(value)?value.join(' '):value),'intent-detail'));
   }
 }
 function renderPreview(r){
   preview.replaceChildren(el('h2',`${r.knowledge_unit_count} relevant ${r.knowledge_unit_count===1?'idea':'ideas'} found`));
   const ideas=el('div',undefined,'preview-ideas');ideas.id='create-relevant-ideas';
   for(const [index,g] of r.knowledge_units.entries()){
     const idea=el('div',undefined,'preview-idea'+(index>=2?' preview-extra':''));idea.append(el('h3',g.canonical_asset.title));
     if(g.canonical_asset.what_it_says)idea.append(el('p',g.canonical_asset.what_it_says));
     if(g.evidence_trail?.length)idea.append(detail('Source evidence',...g.evidence_trail.map(e=>el('p',(sourceData.items.find(s=>s.id===e.source_id)?.title||'Material')+(e.chapter_or_section?' · '+e.chapter_or_section:'')+'\n'+e.evidence,'evidence'))));
     ideas.append(idea);
   }
   preview.append(ideas);
   if(r.knowledge_units.length>2){
     const more=el('button',`View all ${r.knowledge_units.length} ideas`,'preview-more-toggle');more.type='button';
     more.setAttribute('aria-controls',ideas.id);more.setAttribute('aria-expanded','false');
     let expanded=false;
     more.onclick=()=>{expanded=!expanded;ideas.className='preview-ideas'+(expanded?' expanded':'');more.textContent=expanded?'Show fewer ideas':`View all ${r.knowledge_units.length} ideas`;more.setAttribute('aria-expanded',String(expanded));};
     preview.append(more);
   }
   preview.append(el('p','Relevance is a match to your request, not a judgement that the knowledge covers everything you need.','muted'));
   const coverage=el('div',undefined,'source-coverage');coverage.append(el('h3','Source coverage'));
   const rows=r.source_coverage||[...new Set(r.knowledge_units.flatMap(g=>g.source_ids))].map(id=>({title:sourceData.items.find(s=>s.id===id)?.title||'Material',prepared_sections:null,total_sections:null}));
   for(const source of rows){
     const known=Number.isInteger(source.prepared_sections)&&Number.isInteger(source.total_sections);
     const partial=known&&source.prepared_sections<source.total_sections;
     coverage.append(el('p',source.title+' · '+(known?`${source.prepared_sections} of ${source.total_sections} sections ready${partial?' · Partial coverage':''}`:'Section coverage unavailable')+(source.relevant_idea_count?` · ${source.relevant_idea_count} relevant ${source.relevant_idea_count===1?'idea':'ideas'}`:'')));
   }
   if(rows.length)preview.append(coverage);
   if(!r.knowledge_unit_count)preview.append(el('p','No relevant ideas found in this scope. Try adjusting your request or knowledge scope.','muted'));
   const s=r.synthesis_context;
   if(s?.tensions?.length)for(const t of s.tensions)preview.append(el('p',t.reason));
   const resultLabel=interactionDraft.values.output_format.value||mods.items.find(m=>m.id===interactionDraft.values.output_type.value)?.label;
   create.textContent=resultLabel?'Create '+resultLabel.toLowerCase():'Create';
   update.hidden=true;finalAction.hidden=!r.knowledge_unit_count;create.disabled=!r.knowledge_unit_count;
 }
 async function prepare(){
   sync();const payload=workshopRequest(interactionDraft,catalog()),identity=evidenceIdentity(interactionDraft,payload),ticket=++actionRevision;
   interactionDraft={...interactionDraft,prepared:null};finalAction.hidden=true;update.hidden=true;
   preview.replaceChildren(el('p','Finding relevant knowledge…','muted'));
   try{
     const r=await api('/workshops/prepare',{method:'POST',body:payload});
     if(!active()||ticket!==actionRevision||identity!==evidenceIdentity(interactionDraft,payload))return;
     if(!r.prepared_snapshot_id||r.interaction_revision!==interactionDraft.revision)throw Error('Knowledge preview could not be confirmed. Update knowledge before creating.');
     interactionDraft={...interactionDraft,prepared:{identity,revision:interactionDraft.revision,evidence:r}};renderPreview(r);
   }catch(error){if(!active()||ticket!==actionRevision)return;showStale('Knowledge could not be updated. Your request and corrections are kept.');throw error;}
 }
 understanding.hidden=true;
 f.append(original,next,understanding,preview,update,finalAction);container.append(f);main.append(container);
 if(interactionDraft.interpretedRequest!==null&&!draftNeedsInterpretation(interactionDraft)){
   original.open=false;original.children[0].hidden=false;next.hidden=true;renderUnderstanding();
   if(interactionDraft.prepared)renderPreview(interactionDraft.prepared.evidence);
   else if(interactionDraft.clarification.state!=='needed')await prepare();
 }
 const manual=form(async fd=>{sync();let output;try{output=JSON.parse(fd.get('output'));}catch{throw Error('Paste valid structured output JSON.');}const payload=preparedGenerationRequest(interactionDraft,catalog()),ticket=++actionRevision;let r;try{r=await api('/outputs',{method:'POST',body:{brief:payload,output}});}catch(error){if(!active()||ticket!==actionRevision)return;throw error;}if(active()&&ticket===actionRevision)await navigate('work',{id:r.id});});
 const [ol,oi]=field('Structured output result','output','textarea');oi.required=true;manual.append(ol,submit('Validate & save manual output'));
 main.append(detail('Advanced',detail('Developer · manual import',el('p','For existing structured outputs: title, output_type, content, applied_knowledge (asset_id and usage_note), and design_choices. Only reviewed assets can be cited.','muted'),manual),el('p','Unsaved requests stay in this tab until refresh. AI generation uses one Gemini attempt, with no automatic retry, repair or fallback.','muted')));
}
async function savedView(){const active=beginView();heading('MY WORK','Work worth coming back to.','Every saved revision has its own record. Your original work, ideas, and evidence stay intact.');const data=await api('/outputs');if(!active())return;const grid=el('div',undefined,'grid');const roots=new Map();for(const o of data.items)if(!roots.has(o.root_output_id))roots.set(o.root_output_id,o);for(const o of roots.values()){const c=card(o.title,`${o.output_type.replaceAll('_',' ')} · Version ${o.version}`);c.append(el('p',new Date(o.created_at).toLocaleString(),'muted'),button('Open work',()=>navigate('work',{id:o.id})));grid.append(c);}main.append(actions(button('Create something',()=>navigate('workshop'),'primary')),grid);if(!data.count)main.append(el('p','Your work will appear here. Start in Create to make something.','empty'));}
async function outputView(id){const active=beginView();heading('MY WORK','Opening work…','');const o=await api(`/outputs/${id}`);if(!active())return;const quality=await api(`/outputs/${id}/quality`);if(!active())return;heading('VERSION '+o.version,o.title,`${o.output_type.replaceAll('_',' ')} · Saved ${new Date(o.created_at).toLocaleString()}`);const review=card('Quality review',quality.validation_status.replaceAll('_',' '));review.append(el('p',o.provider==='manual'?'Manually supplied or edited':o.provider+' / '+o.model),el('p',quality.note),list(quality.issues.map(i=>i.message)));if(quality.timing_checks)review.append(list(quality.timing_checks.map(c=>`${c.criterion.replaceAll('_',' ')}: ${c.status} · Requested: ${c.requested_minutes??'unknown'} min · Calculated: ${c.calculated_minutes??'unknown'} min`)));const exportLink=el('a','Export Markdown');exportLink.href=`/outputs/${id}/export`;main.append(actions(button('← My work',()=>navigate('outputs')),exportLink),el('article',o.content,'reading'));const evidence=detail('Ideas and evidence used');main.append(evidence);for(const ref of o.applied_knowledge){const g=o.knowledge_snapshot.find(g=>g.canonical_asset.id===ref.asset_id);const c=card(g?.canonical_asset.title||ref.asset_id,ref.usage_note);c.append(detail('Material evidence',...(g?.evidence_trail||[]).map(e=>el('p',`${e.source_id} · ${e.chunk_id}\n${e.evidence}`,'evidence'))));evidence.append(c);}main.append(detail('Review and design choices',review,list(o.design_choices.length?o.design_choices:['No additional design choices recorded. Review before use.'])));
 const revise=form(async fd=>{const body=revisionPayload(fd,o);const n=await api(`/outputs/${id}/revise`,{method:'POST',body});if(!active())return;if(!await navigate('work',{id:n.id}))return;message(`Saved version ${n.version}; the original is unchanged.`);});const [il,ii]=field('Revision instruction','instruction');ii.required=true;ii.minLength=2;const [ml,mi]=field('Save my manual edits (no AI call)','manual');mi.type='checkbox';mi.checked=true;ml.className='check';const [tl,ti]=field('Title','title','input',o.title),[cl,ci]=field('Edited content','content','textarea',o.content),[dl,di]=field('Design choices — one per line','choices','textarea',o.design_choices.join('\n'));ci.rows=12;revise.append(il,ml,tl,cl,dl,submit('Save new version'));main.append(detail('Revise this work',revise));const history=await api(`/outputs/${id}/history`);if(!active())return;const h=card('Version history');const diff=el('pre');for(const v of history.items)h.append(actions(button(`Open version ${v.version}`,()=>navigate('work',{id:v.id})),v.id!==id?button(`Compare v${o.version} → v${v.version}`,async()=>{const r=await api(`/outputs/${id}/compare/${v.id}`);diff.textContent=`Changed: ${r.changed_fields.join(', ')||'None'}\n\n${r.content_diff}`;}):el('span','Current','badge')));h.append(diff);main.append(h,actions(button('Delete work and version history',async()=>{if(!confirm('Delete this work and every revision? This cannot be undone.'))return;await api(`/outputs/${id}?entire_history=true`,{method:'DELETE'});if(!active())return;await navigate('outputs',{replace:true});},'danger')));}
async function settingsView(){const active=beginView();heading('SETTINGS','Your data, in your hands.','Keep backups private: they contain your materials and saved work.');const [usage,integrity]=await Promise.all([api('/usage'),api('/data/integrity')]);if(!active())return;const aiState=!usage.configured?'Unavailable — Gemini key required':!usage.free_tier_confirmed?'Blocked — free-project confirmation required':usage.paused?'Paused':'Ready for explicit requests';const c=card('AI usage',`${usage.calls_today} / ${usage.daily_call_limit} daily call budget used`);c.append(list([`Gemini key: ${usage.configured?'Configured':'Not configured'}`,`Free-project confirmation: ${usage.free_tier_confirmed?'Confirmed':'Required before AI calls'}`,`State: ${aiState}`]),el('p',usage.reason||usage.note,'muted'));if(usage.paused&&!usage.daily_limit_reached)c.append(button('Resume after quota reset',async()=>{await api('/usage/resume',{method:'POST'});if(!active())return;await navigate('settings',{replace:true});}));const e=el('a','Download complete private backup');e.href='/data/export';const data=card('Export & integrity',integrity.ok?'No broken record links or missing material files detected.':`${integrity.issues.length} integrity issue(s) require attention.`);data.append(e,list(integrity.issues.map(i=>`${i.id}: ${i.problem}`)));main.append(c,data);if(csrfToken()){logoutButton.hidden=false;main.append(logoutButton);}}
const views={home:homeView,library:libraryView,knowledge:knowledgeView,workshop:workshopView,outputs:savedView,settings:settingsView,material:sourceView,work:outputView};
const logoutButton = el('button','Sign out');logoutButton.id='beta-logout';logoutButton.hidden=true;document.body.append(logoutButton);
if (logoutButton && csrfToken()) {
  logoutButton.onclick = async () => {
    logoutButton.disabled = true;
    try {
      const response = await apiFetch('/logout', {method: 'POST'});
      if (response.ok || response.redirected) window.location.assign('/login');
      else throw new Error('Unable to sign out. Try again.');
    } catch (error) {
      message(error.message, true);
      logoutButton.disabled = false;
    }
  };
}

const router=createNavigation(window,route=>run(async()=>{
 captureDraft();
 if(route.newDraft){interactionDraft=route.newDraft;delete route.newDraft;}
 const previousLibrary=state.library;state.view=route.view;state.library=route.library||null;
 if(route.view==='knowledge'){exploreState=route.exploreState||freshExplore();route.exploreState=exploreState;explorePicker=!!route.picker;}
 if(['workshop','knowledge'].includes(route.view)){const materials=route.materials||[];if(previousLibrary!==state.library||JSON.stringify(materials)!==JSON.stringify(createMaterials||[]))state.selected.clear();createMaterials=materials;state.source=route.source||(materials.length===1?materials[0]:null);if(route.view==='knowledge'&&exploreState.selectedIds)state.selected=new Set(exploreState.selectedIds);else if(route.selectedIds)state.selected=new Set(route.selectedIds);}
 const parent={knowledge:'library',material:'library',work:'outputs'}[route.view]||route.view;
 for(const b of document.querySelectorAll('nav button')){if(b.dataset.view===parent)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');}
 const pending=views[route.view](route.id,route),revision=viewRevision;await pending;if(revision===viewRevision)main.focus();
}));
window.addEventListener('pagehide',captureDraft);
router.start();
