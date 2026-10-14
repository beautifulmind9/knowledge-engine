import {MATERIAL_EXTENSIONS, validateMaterial, suggestedMaterialTitle, newMaterialAddBatch, selectMaterialFiles, addMaterials} from './material-add.js';
import {availableAIAllowance} from './knowledge-build.js';
import {createMaterialPreparation} from './material-preparation.js';
import { revisionPayload } from './output-revision.js';
import {renderGroundedAnswer, observeAnswerTableOverflow} from './answer-renderer.js';
import {api, apiFetch, csrfToken} from './api.js';
import {createNavigation} from './navigation.js';
import {newInteractionDraft, captureRequest, correctDraft, interpretDraft, draftNeedsInterpretation, workshopRequest, evidenceIdentity, confirmDraft, preparedGenerationRequest} from './interaction-draft.js';
import { PAGE_SIZE, filterUnits, createSearchController } from './knowledge-browser.js';
import {beginProcessingStatus,updateProcessingStatus,endProcessingStatus,getProcessingStatus,subscribeProcessingStatus,renderProcessingStatus,attachProcessingAnnouncer,announceProcessingStatus} from './processing-status.js';
const main=document.querySelector('main'), feedback=document.querySelector('#feedback');
const processingRegion=document.querySelector('#processing-status');
attachProcessingAnnouncer(document.querySelector('#processing-announcer'));
subscribeProcessingStatus(status=>renderProcessingStatus(processingRegion,status));
let interactionDraft=newInteractionDraft(),createMaterials=null,viewRevision=0,foregroundBuild=null,libraryCollectionRefresh=null,preparationBatch=null;
const preparationOutcomes=new Map();
function beginView(){const revision=++viewRevision;return ()=>revision===viewRevision;}
let homeDraft=newInteractionDraft(),exploreState=null,explorePicker=false,materialAddDraft=null;
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
async function run(fn,b){if(b)b.disabled=true;main.setAttribute('aria-busy','true');message('Working…');let revision=viewRevision;try{const pending=fn();revision=viewRevision;if(getProcessingStatus())message('');await pending;if(revision!==viewRevision)return;if(feedback.textContent==='Working…')message('');}catch(e){if(revision===viewRevision)message(e.message,true);}finally{if(b)b.disabled=false;if(revision===viewRevision)main.removeAttribute('aria-busy');}}
function field(label,name,kind='input',value=''){const l=el('label',label),i=el(kind);i.name=name;if(kind==='textarea')i.rows=4;i.value=value;l.append(i);return [l,i];}
function select(label,values,current='',multiple=false){const [l,s]=field(label,label,'select');s.multiple=multiple;for(const [id,name] of values){const o=el('option',name);o.value=id;o.selected=Array.isArray(current)?current.includes(id):id===current;s.append(o);}return [l,s];}
function form(onSubmit){const f=el('form');f.onsubmit=e=>{e.preventDefault();return run(()=>onSubmit(new FormData(f)),f.querySelector('[type=submit]'));};return f;}
function submit(text){const b=el('button',text,'primary');b.type='submit';return b;}
function heading(kicker,title,description){main.className='';main.updateMaterialPreparation=null;main.refreshMaterialStatus=null;main.materialId=null;main.captureExplore=null;main.exploreContext=null;main.refreshMaterialAdd=null;libraryCollectionRefresh=null;const signout=main.querySelector('#beta-logout');if(signout){signout.hidden=true;document.body.append(signout);}main.replaceChildren(el('div',kicker,'kicker'),el('h1',title),el('p',description,'intro'));}
function card(title,description){const c=el('section',undefined,'card');c.append(el('h3',title));if(description)c.append(el('p',description));return c;}
function actions(...buttons){const d=el('div',undefined,'actions');d.append(...buttons);return d;}
function detail(title,...nodes){const d=el('details');d.append(el('summary',title),...nodes);return d;}
function requireValidFile(input,action){action.disabled=true;input.onchange=()=>{try{validateMaterial(input.files?.[0]);action.disabled=false;message('');}catch(error){action.disabled=true;message(error.message,true);}};}
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
function preparationLabel(completed,total){
 if(!Number.isInteger(completed)||!Number.isInteger(total))return 'Preparation progress unavailable';
 if(!total||!completed)return 'Not yet prepared';
 return completed===total?'Prepared':'Partly prepared';
}
const libraryReadiness={added:'Added',ready_to_build:'Preparation not complete',partly_ready:'Partly ready',ready:'Ready',unknown:'Status unavailable'};
function rowAction(summary){
 if(!summary)return 'Open material';
 if(summary.has_usable_knowledge)return 'Explore knowledge';
 if(summary.attention_category==='build_stopped'||summary.attention_category==='build_unconfirmed'||summary.recovery?.some(item=>item.allowed))return 'Open material';
 if(summary.readiness==='added'&&summary.next_action==='attach_file')return 'Finish adding';
 if(summary.readiness==='added'&&summary.next_action==='read_source')return 'Read source';
 return 'Open material';
}
function renderLibraryRow(source,summary,summaryUnavailable=false,batchOutcome=null){
 const row=el('article',undefined,'library-row');
 const title=el('h2',source.title,'library-row-title');row.append(title);
 const action=rowAction(summary);
 if(action==='Explore knowledge'){
  const materialLink=el('a','Open material','library-row-material-link');materialLink.href='#/library/material/'+encodeURIComponent(source.id);materialLink.onclick=event=>{event.preventDefault();return run(()=>navigate('material',{id:source.id}));};title.append(materialLink);
 }
 if(source.title_origin==='filename')row.append(el('p','Temporary name from filename','library-row-author'));
 if(source.author?.trim())row.append(el('p',source.author,'library-row-author'));
 if(summary){
  const queuedForBatch=batchOutcome?.category==='not_started'&&!preparationBatch?.finished;
  const activelyPreparing=batchOutcome?.category==='running';
  const interrupted=['provider_unavailable','preparation_timeout','failed','uncertain','status_unavailable'].includes(batchOutcome?.category)||(!activelyPreparing&&!queuedForBatch&&['build_stopped','build_unconfirmed'].includes(summary.attention_category));
  row.append(el('p',activelyPreparing||queuedForBatch?'Preparing':libraryReadiness[summary.readiness]||'Status unavailable','library-row-readiness'));
  if(activelyPreparing&&Number.isInteger(summary.completed_parts)&&summary.total_parts>0){
   const progress=el('progress');progress.max=summary.total_parts;progress.value=summary.completed_parts;progress.setAttribute('aria-label',`Preparation progress for ${source.title}`);row.append(progress,el('p',`${Math.round(100*summary.completed_parts/summary.total_parts)}% prepared`,'library-row-coverage'));
  } else if(interrupted)row.append(el('p','Needs attention · Progress saved','library-row-attention'));
  else if(queuedForBatch)row.append(el('p','Included in this preparation','library-row-coverage'));
  if(!activelyPreparing&&!queuedForBatch&&summary.has_usable_knowledge)row.append(el('p','Knowledge available','library-row-coverage'));
  if(!activelyPreparing&&!queuedForBatch&&summary.readiness==='partly_ready')row.append(el('p','Partly prepared','library-row-coverage'));
  if(summary.readiness==='unknown')row.append(el('p','Preparation progress unavailable','library-row-coverage'));
  if(summary.readiness==='ready'&&!summary.has_usable_knowledge)row.append(el('p','No usable knowledge is available from this material yet.','library-row-operation'));
  if(summary.attention_category&&!interrupted)row.append(el('p',`Needs attention: ${summary.attention_message||'This material needs attention.'}`,'library-row-attention'));
  if(summary.operation==='build_unconfirmed'&&summary.attention_category!=='build_unconfirmed')row.append(el('p','Previous build has not reported completion.','library-row-operation'));
 }else{
  row.append(el('p',summaryUnavailable?'Readiness unavailable':'Status unavailable','library-row-readiness'));
  row.append(el('p','Preparation progress unavailable','library-row-coverage'));
  if(summaryUnavailable)row.append(el('p','Current status could not be loaded. Open the material to check it.','library-row-operation'));
 }
 const controls=actions();
 const buttonLabel=action==='Explore knowledge'?'Explore':action;
 controls.append(button(buttonLabel,async()=>{
  if(action==='Explore knowledge')return navigate('knowledge',{library:source.library_id||state.library,materials:[source.id],source:source.id,exploreState:freshExplore(exploreState?.query||'')});
  if(action==='Finish adding'||action==='Open material')return navigate('material',{id:source.id});
  if(action==='Read source'){
   const task=beginProcessingStatus({label:'Reading your material',detail:'Your original file stays safely attached to this material.'});
   try{await api(`/sources/${source.id}/process`,{method:'POST'});}finally{endProcessingStatus(task);}
   if(!await navigate('library',{replace:true}))return;
   await navigate('material',{id:source.id});await startPreparation([source.id]);return;
  }
  return navigate('material',{id:source.id});
 },'primary'));
 row.append(controls);return row;
}
async function homeView(){beginView();heading('HOME','What would you like to do?','What are you trying to learn, decide, make, plan or figure out?');
 const entry=el('section',undefined,'home-intent'),[label,input]=field('Your request','home_request','textarea',homeDraft.originalRequest);input.rows=3;input.placeholder='Start with what’s on your mind.';
 input.oninput=()=>{main.querySelector('#create-handoff')?.remove();homeDraft=captureRequest(homeDraft,input.value);};
 entry.append(label,actions(button('Ask & Explore',()=>navigate('knowledge',{library:null,materials:[],source:null,exploreState:freshExplore(input.value)})),button('Create something',()=>input.value.trim()?openCreate({request:input.value,materials:[],selectedIds:[]}):openCreate())),el('p','Choose what you’d like to do with your request.','muted'));main.append(entry);
 const choices=el('div',undefined,'home-choices');for(const [title,description,view] of [['Add to my library','Bring in material you want to use.','library'],['Continue my work','Return to something created earlier.','outputs']]){const row=el('section');row.append(button(title,()=>navigate(view,view==='library'?{add:true}:{})),el('p',description));choices.append(row);}main.append(choices);}
function materialAddSurface(libs,active){
 if(!materialAddDraft?.items?.length)materialAddDraft=newMaterialAddBatch(libs,state.library);
 const batch=materialAddDraft;
 const surface=card('Add material','Choose one or more PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON files · up to 50 MB (50,000,000 bytes) each');surface.id='material-add';
 const [fileLabel,fileInput]=field('Choose one or more material files','file');fileInput.type='file';fileInput.multiple=true;fileInput.accept=MATERIAL_EXTENSIONS.join(',');
 const confirmation=el('div');confirmation.id='material-confirmation';
 surface.append(fileLabel,confirmation);
 function renderConfirmation(){
  confirmation.replaceChildren();fileInput.disabled=batch.busy;
  if(!batch.items.length&&!batch.invalidFiles.length)return;
  confirmation.append(el('h3','Here’s what we found'),el('p','KE will read and prepare this material so you can ask questions, explore ideas and use it in your work.','muted'));
  if(batch.items.length){
   const destinationName=libs.find(l=>l.id===batch.libraryId)?.name||batch.libraryName;
   confirmation.append(el('p',`${batch.items.length} ${batch.items.length===1?'material':'materials'} · ${destinationName}`,'file-facts'));
   if(batch.items.some(item=>item.sourceId&&!item.read))confirmation.append(el('p','Some materials still need attention. Completed materials are kept; retrying will resume unfinished items.','muted'));
   for(const [index,draft] of batch.items.entries()){
    const item=el('section',undefined,'material-batch-item');
    item.append(el('p',`${draft.file.name} · ${draft.file.name.split('.').at(-1).toUpperCase()} · ${draft.file.size<1024?draft.file.size+' bytes':draft.file.size<1024*1024?(draft.file.size/1024).toFixed(1)+' KiB':(draft.file.size/1024/1024).toFixed(2)+' MiB'}`,'file-facts'));
    const [titleLabel,title]=field('Title · suggested from filename',batch.items.length===1?'title':'title-'+index,'input',draft.title);title.required=true;title.maxLength=500;title.disabled=batch.busy||!!draft.sourceId;title.oninput=()=>{draft.title=title.value;draft.titleUserConfirmed=true;};item.append(titleLabel);
    const [authorLabel,author]=field('Author / creator (optional)',batch.items.length===1?'author':'author-'+index,'input',draft.author);author.disabled=batch.busy||!!draft.sourceId;author.oninput=()=>{draft.author=author.value;draft.authorUserConfirmed=true;};item.append(detail('Optional details',authorLabel));
    if(draft.error){const error=el('p',draft.error.message,'error');error.setAttribute('role','alert');item.append(error);}
    if(draft.read)item.append(el('p','Added and read.','muted'));
    if(draft.sourceId)item.append(button('Open material',()=>navigate('material',{id:draft.sourceId,library:draft.libraryId})));
    if(draft.sourceId&&!draft.read){const needsReplacement=draft.uploaded&&draft.readFailure==='ocr_required';const [replacementLabel,replacement]=field(needsReplacement?'Choose a different file with selectable text':'Choose a replacement file','replacement_file-'+index);replacement.type='file';replacement.accept=MATERIAL_EXTENSIONS.join(',');replacement.disabled=batch.busy;replacement.onchange=()=>{try{validateMaterial(replacement.files?.[0]);draft.file=replacement.files[0];draft.uploaded=false;draft.readFailure=null;draft.replacementSelected=true;draft.error=null;renderConfirmation();}catch(error){message(error.message,true);}};item.append(replacementLabel);}
    confirmation.append(item);
   }
   const destination=el('p',`Destination · ${destinationName}`,'material-batch-destination');confirmation.append(destination);
   if(!batch.items.some(item=>item.sourceId||item.read)){
    const change=detail('Change destination');let nameLabel,name;
    if(libs.length){const [label,selectInput]=select('Destination',[...libs.map(l=>[l.id,l.name]),['','New library']],batch.libraryId||'');selectInput.setAttribute('aria-label','Destination');change.append(label);selectInput.disabled=batch.busy;selectInput.onchange=()=>{batch.libraryId=selectInput.value||null;for(const item of batch.items)item.libraryId=batch.libraryId;nameLabel.hidden=!!batch.libraryId;destination.textContent='Destination · '+(libs.find(l=>l.id===batch.libraryId)?.name||batch.libraryName);};}
    [nameLabel,name]=field('New library name','destination_name','input',batch.libraryName);name.required=true;name.maxLength=200;name.disabled=batch.busy;nameLabel.hidden=!!batch.libraryId;name.oninput=()=>{batch.libraryName=name.value;for(const item of batch.items)item.libraryName=name.value;destination.textContent='Destination · '+name.value;};change.append(nameLabel);confirmation.append(change);
   }
  }
  for(const invalid of batch.invalidFiles){const error=el('p',`${invalid.name}: ${invalid.message}`,'error');error.setAttribute('role','alert');confirmation.append(error);}
  const pendingItems=batch.items.filter(item=>!item.read);
  const onlyItem=batch.items.length===1?batch.items[0]:null;
  const actionLabel=onlyItem?(onlyItem.uploaded&&onlyItem.readFailure==='ocr_required'&&!onlyItem.replacementSelected?'Choose a different file':onlyItem.replacementSelected?'Use replacement file':onlyItem.read?'Open material':onlyItem.uploaded?'Retry reading':onlyItem.sourceId?'Retry upload':onlyItem.error?'Retry Add material':'Add material'):`${batch.items.some(item=>item.sourceId||item.read)?'Retry':'Add'} ${pendingItems.length} ${pendingItems.length===1?'material':'materials'}`;
  const add=button(actionLabel,async()=>{
   if(onlyItem?.uploaded&&onlyItem.readFailure==='ocr_required'&&!onlyItem.replacementSelected){confirmation.querySelector('[name="replacement_file-0"]')?.click();return;}
   if(onlyItem?.read)return navigate('material',{id:onlyItem.sourceId,library:onlyItem.libraryId});
   if(pendingItems.some(item=>!item.title.trim())){confirmation.querySelector('[name="title-'+batch.items.findIndex(item=>!item.title.trim())+'"]')?.reportValidity();return;}
   let addActivity=null;
   const pending=addMaterials(batch,api,file=>{const data=new FormData();data.append('file',file);return data;},text=>{
    if(!active())return;
    const label=text.startsWith('Reading')?'Reading your material':'Adding your material';
    if(!addActivity)addActivity=beginProcessingStatus({label,detail:'Each material is added and read separately.'});
    else updateProcessingStatus(addActivity,{label,detail:'Each material is added and read separately.'});
   });
   renderConfirmation();
   let result;try{result=await pending;}finally{if(addActivity)endProcessingStatus(addActivity);}
   if(!active())return;
   const readable=result.results.filter(item=>item.ok).map(item=>item.draft.sourceId);
   if(readable.length){
    if(result.failed===0&&!batch.invalidFiles.length)materialAddDraft=null;
    await navigate('material',{id:readable[0],library:batch.libraryId});
    if(result.failed||batch.invalidFiles.length)message('Some files could not be added. Saved materials are kept; return to Library to finish adding the others.',true);
    await startPreparation(readable);return;
   }
   renderConfirmation();await navigate('library',{add:true,replace:true});
   message('Material addition is incomplete. Saved records are kept; choose the supported next action below.',true);
  },'primary');add.disabled=batch.busy||!pendingItems.length;
  const clearSelection=()=>{batch.items=[];batch.invalidFiles=[];materialAddDraft=null;fileInput.value='';renderConfirmation();};
  const controls=actions(add);if(batch.items.every(item=>!item.sourceId&&!item.read))controls.append(button('Cancel',clearSelection));else if(!pendingItems.length)controls.append(button('Clear results',clearSelection));confirmation.append(controls);
 }
 fileInput.onchange=()=>{const selected=Array.from(fileInput.files||[]);selectMaterialFiles(batch,selected);renderConfirmation();if(batch.invalidFiles.length)message(selected.length===1&&!batch.items.length?batch.invalidFiles[0].message:'Unsupported or empty files were left out. The valid files can still be added.',true);else message('');};
 main.refreshMaterialAdd=renderConfirmation;renderConfirmation();return surface;
}
async function libraryView(_id,route={}){const active=beginView();heading('LIBRARY','Your library','Material, ideas and work in one place.');const libs=await libraries();if(!active())return;
 if(libs.length>1){const [l,s]=select('Filter by library',[['','All libraries'],...libs.map(l=>[l.id,l.name])],state.library||'');s.onchange=()=>{state.library=s.value||null;state.source=null;state.selected.clear();if(!materialAddDraft?.items?.length)materialAddDraft=null;run(()=>navigate('library',{replace:true}));};main.append(l);}
 const sources=libs.length?await sourceItems():[];if(!active())return;
 let summaries=[],summaryUnavailable=false;
 if(sources.length){try{summaries=await api('/sources/summaries'+(state.library?'?library_id='+encodeURIComponent(state.library):''));}catch{summaryUnavailable=true;}}
 if(!active())return;
 const summaryById=new Map(summaries.map(summary=>[summary.source_id,summary]));
 const collection=el('section',undefined,'library-collection');
 const summaryLine=el('div',undefined,'library-summary-line');
 const collectionHeader=el('div',undefined,'library-collection-header');collectionHeader.append(el('div','YOUR COLLECTION','kicker'),summaryLine,actions(button('Add material',()=>{const add=main.querySelector('.library-add');if(add){add.open=true;add.scrollIntoView({behavior:'smooth',block:'start'});add.querySelector('input[type=file]')?.focus();}},'primary'),button('Ask & Explore',()=>navigate('knowledge',{materials:[],source:null}))));
 collection.append(collectionHeader);
 const addDetails=detail('Add material',materialAddSurface(libs,active));addDetails.className='library-add';addDetails.open=route.add||!sources.length||!!materialAddDraft?.items?.length;collection.append(addDetails);
 if(!sources.length){const empty=el('p','Choose a file to add material to your library. You can organize it into libraries later.','empty');empty.id='library-empty';collection.append(empty);}
 const batchSummary=el('section',undefined,'library-batch-summary');collection.append(batchSummary);
 const create=form(async fd=>{const lib=await api('/libraries',{method:'POST',body:{name:fd.get('name'),description:fd.get('description')}});if(!active())return;state.library=lib.id;if(!materialAddDraft?.items?.length)materialAddDraft=null;if(!await navigate('library',{add:true,replace:true}))return;message('Library created.');});for(const [label,name] of [['Library name','name'],['Description','description']]){const [l,i]=field(label,name);i.required=name==='name';create.append(l);}create.append(submit('Create library'));collection.append(detail('Create a library',create));
 const grid=el('div',undefined,'library-rows');grid.setAttribute('aria-label','Materials');collection.append(grid);
 const renderCards=()=>{
  const effective=source=>preparationBatch?.outcomes.get(source.id)?.summary||summaryById.get(source.id);
  const currentReady=sources.filter(source=>effective(source)?.readiness==='ready').length;
  const currentPreparing=sources.filter(source=>['running','not_started'].includes(preparationBatch?.outcomes.get(source.id)?.category)&&!preparationBatch?.finished).length;
  const currentAttention=sources.filter(source=>['provider_unavailable','preparation_timeout','failed','uncertain','status_unavailable'].includes(preparationBatch?.outcomes.get(source.id)?.category)||(effective(source)?.attention_category&&!['completed','running'].includes(preparationBatch?.outcomes.get(source.id)?.category))).length;
  summaryLine.replaceChildren(el('span',`${sources.length} ${sources.length===1?'material':'materials'}`),el('span',`${currentReady} ready`));if(currentPreparing)summaryLine.append(el('span',`${currentPreparing} preparing`));if(currentAttention)summaryLine.append(el('span',`${currentAttention} need attention`));
  batchSummary.replaceChildren();
  if(preparationBatch?.finished){
   const failed=sources.filter(source=>['provider_unavailable','preparation_timeout','failed','uncertain','status_unavailable'].includes(preparationBatch.outcomes.get(source.id)?.category));
   const incomplete=sources.filter(source=>{const s=effective(source);return s&&s.readiness!=='ready'&&['build_knowledge','continue_building'].includes(s.next_action)&&s.operation!=='build_unconfirmed';});
   if(failed.length||preparationBatch.status==='daily_allowance'||preparationBatch.status==='allowance_unavailable'){
    const affected=failed.length===1?'1 material needs another attempt.':`${failed.length} materials need another attempt.`;
    const copy=preparationBatch.status==='daily_allowance'?`${currentReady} ${currentReady===1?'material is':'materials are'} ready. Preparation is paused for today.`:preparationBatch.status==='allowance_unavailable'?`${currentReady} ${currentReady===1?'material is':'materials are'} ready. Preparation could not check the shared allowance.`:`${currentReady} ${currentReady===1?'material is':'materials are'} ready. ${affected}`;
    batchSummary.append(el('p',copy));if(incomplete.length&&preparationBatch.status!=='daily_allowance')batchSummary.append(button('Continue incomplete materials',()=>startPreparation(incomplete.map(source=>source.id)),'primary'));
   }
  }
  grid.replaceChildren();for(const source of sources)grid.append(renderLibraryRow(source,effective(source),summaryUnavailable,preparationBatch?.outcomes.get(source.id)));
 };
 renderCards();libraryCollectionRefresh=renderCards;main.append(collection);
}
async function startPreparation(sourceIds){
 if(foregroundBuild)return;
 if(feedback.textContent==='Working…')message('');
 preparationBatch={sourceIds:[...new Set(sourceIds)],outcomes:new Map(),finished:false,status:'running'};
 const batchSize=preparationBatch.sourceIds.length;
 const activityId=beginProcessingStatus({label:batchSize>1?'Preparing your library':'Preparing your material',detail:batchSize>1?`0 of ${batchSize} materials ready. New knowledge appears as it becomes available. You can keep using Knowledge Engine in this tab.`:'New knowledge appears as it becomes available. You can keep using Knowledge Engine in this tab.',onStop:()=>{foregroundBuild?.stop();updateProcessingStatus(activityId,{stopRequested:true,onStop:null,detail:'Finishing the current step before stopping.'});}});
 let session;
 session=createMaterialPreparation({sourceIds:preparationBatch.sourceIds,api,onSource:async()=>{},onProgress:snapshot=>{
  for(const [id,outcome] of snapshot.outcomes)preparationOutcomes.set(id,outcome);
  preparationBatch.outcomes=new Map(snapshot.outcomes);preparationBatch.status=snapshot.status;
  const readyCount=[...snapshot.outcomes.values()].filter(outcome=>outcome.summary?.readiness==='ready').length;
  updateProcessingStatus(activityId,{completed:snapshot.completedWork,total:snapshot.totalWork||null,detail:batchSize>1?`${readyCount} of ${batchSize} materials ready. New knowledge appears as it becomes available. You can keep using Knowledge Engine in this tab.`:'New knowledge appears as it becomes available. You can keep using Knowledge Engine in this tab.'});
  libraryCollectionRefresh?.();
  try{main.updateMaterialPreparation?.();}catch{session?.stop('callback_failure');}
 }});
 foregroundBuild=session;
 let result;
 try{result=await session.run();}catch{result={...session.snapshot(),status:'status_unavailable'};}finally{
  if(foregroundBuild===session)foregroundBuild=null;
  for(const [id,outcome] of session.snapshot().outcomes)preparationOutcomes.set(id,outcome);
  try{await main.refreshMaterialStatus?.();}catch{/* Status remains explicitly unavailable until it can be checked. */}
  try{main.updateMaterialPreparation?.();}catch{/* The server summary remains authoritative. */}
  const final=result||session.snapshot();
  preparationBatch.outcomes=new Map(session.snapshot().outcomes);preparationBatch.status=final.status;preparationBatch.finished=true;
  libraryCollectionRefresh?.();
  if(final.status==='completed'){announceProcessingStatus('Your material is ready.');endProcessingStatus(activityId);}
  else if(final.status==='provider_unavailable')updateProcessingStatus(activityId,{label:'Preparation paused',detail:'The AI service was temporarily unavailable. Your progress is saved.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='preparation_timeout')updateProcessingStatus(activityId,{label:'Preparation paused',detail:'The last preparation request did not finish in time.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='daily_allowance')updateProcessingStatus(activityId,{label:'Preparation paused for today',detail:'Today’s shared allowance is used. Your progress is saved.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='uncertain')updateProcessingStatus(activityId,{label:'Preparation needs confirmation',detail:'The last request could not be confirmed.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='status_unavailable')updateProcessingStatus(activityId,{label:'Preparation status unavailable',detail:'Your confirmed progress is saved. Check the material status before continuing.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='stopped'||final.status==='left')updateProcessingStatus(activityId,{label:'Preparation stopped',detail:final.status==='left'?'You can return to the material to continue.':'You can continue from the material page.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='failed')updateProcessingStatus(activityId,{label:'Preparation stopped',detail:'Your progress is saved. Continue preparing when you are ready.',completed:final.completedWork,total:final.totalWork||null});
  else if(final.status==='incomplete'){
   updateProcessingStatus(activityId,{label:'Batch attempt complete',detail:'Completed progress is saved. See your Library for each material’s current status.',completed:final.completedWork,total:final.totalWork||null});
  }
  else endProcessingStatus(activityId);
  if(final.status!=='completed'&&final.status!=='idle')updateProcessingStatus(activityId,{onStop:null,stopRequested:false});
 }
}
async function sourceView(id){
 const active=beginView(),previousSource=state.source;state.source=id;
 heading('LIBRARY · MATERIAL','Opening material…','');
 const [source,initialSummary,libraryData]=await Promise.all([api(`/sources/${id}`),api(`/sources/${id}/summary`),libraries()]);
 if(!active())return;
 let summary=initialSummary,usage=null,previewRevision=0,lastPreviewCount=-1;
 const canPrepare=()=>['build_knowledge','continue_building'].includes(summary.next_action)&&summary.operation!=='build_unconfirmed'&&Number.isInteger(summary.total_parts)&&summary.total_parts>summary.completed_parts;
 if(canPrepare())usage=await api('/usage').catch(()=>null);
 if(!active())return;
 const addDraft=materialAddDraft?.items?.find(item=>item.sourceId===id);
 if(addDraft){addDraft.uploaded=!!source.file_path;addDraft.read=summary.read_state==='read';addDraft.readFailure=summary.attention_category;}
 heading('LIBRARY · MATERIAL',source.title,source.author||'');main.className='material-workspace';main.materialId=id;
 const header=el('section',undefined,'material-header');header.append(...Array.from(main.children));
 const identityHint=source.title_origin==='material_text'?'Found in the material':source.title_origin==='document_metadata'?'From the document':source.title_origin==='filename'?'Temporary name from filename':'';
 if(identityHint)header.append(el('p',identityHint,'material-identity-origin'));
 const authorHint=source.author_origin==='material_text'?'Author found in the material':source.author_origin==='material_text_suggested'?'Author suggested from the material — please check':source.author_origin==='document_metadata'?'Author from the document':'';
 if(source.author&&authorHint)header.append(el('p',authorHint,'material-identity-origin'));
 if(summary.read_state==='read'&&!source.author&&source.author_origin!=='user_confirmed')header.append(el('p','Author not confirmed','muted'));
 if(source.identity_conflict)header.append(el('p','The document details differ from the title shown. Review the identity if needed.','muted'));
 const needsIdentityReview=source.title_origin==='filename'||source.author_origin==='material_text_suggested'||(summary.read_state==='read'&&!source.author&&source.author_origin!=='user_confirmed');
 const identityEdit=detail(needsIdentityReview?'Review identity':'Edit identity');identityEdit.className='material-identity-edit';
 const identityForm=form(async fd=>{await api(`/sources/${encodeURIComponent(id)}/identity`,{method:'PUT',body:{title:fd.get('identity_title'),author:fd.get('identity_author')||null}});if(active())await navigate('material',{id,replace:true});});
 const [identityTitleLabel,identityTitle]=field('Title','identity_title','input',source.title);identityTitle.required=true;identityTitle.maxLength=500;
 const [identityAuthorLabel,identityAuthor]=field('Author / creator (optional)','identity_author','input',source.author||'');identityAuthor.maxLength=500;
 identityForm.append(identityTitleLabel,identityAuthorLabel,submit('Save identity'));identityEdit.append(identityForm);header.append(identityEdit);
 header.append(button('← Library',()=>navigate('library')));main.append(header);
 const status=el('section',undefined,'material-status');status.setAttribute('aria-label','Material preparation');
 const statusTitle=el('h2'),coverage=el('p',undefined,'material-coverage'),statusNote=el('p',undefined,'muted'),attention=el('p',undefined,'material-attention'),progress=el('progress');progress.setAttribute('aria-label','Material preparation progress');
 const preparationActions=actions();status.append(statusTitle,coverage,progress,statusNote,attention,preparationActions);main.append(status);
 const workspace=el('div',undefined,'material-workspace-grid'),preview=el('section',undefined,'material-knowledge'),rail=el('section',undefined,'material-context');
 const use=el('section',undefined,'material-use-actions');use.setAttribute('aria-label','Use this knowledge');rail.append(use);workspace.append(preview,rail);main.append(workspace);
 const libraryName=libraryData.find(item=>item.id===source.library_id)?.name||null;
 const sameSourceContext=previousSource===id&&createMaterials?.includes(id),selectedForSource=sameSourceContext?[...state.selected]:[];
 const openScopedKnowledge=(query='')=>navigate('knowledge',{source:id,materials:[id],library:source.library_id||null,exploreState:sameSourceContext&&exploreState?exploreState:freshExplore(query),selectedIds:selectedForSource});
 const renderUse=()=>{
  use.replaceChildren();if(!summary.has_usable_knowledge)return;
  use.append(el('h2','Put this knowledge to work'),button('Ask this source',()=>openScopedKnowledge('What does this material teach?'),'primary'),button('Explore ideas',()=>openScopedKnowledge()),button('Use in Create',()=>openCreate({request:sameSourceContext&&exploreState?.query||interactionDraft.originalRequest||'',materials:[id],library:source.library_id||null,selectedIds:selectedForSource})));
 };
 async function loadKnowledge(){
  const ticket=++previewRevision;preview.replaceChildren(el('h2','Knowledge from this material'));
  if(!summary.has_usable_knowledge){preview.append(el('p',summary.readiness==='ready'?'No usable knowledge is available from this material yet.':'Knowledge will appear here as your material is prepared.','material-knowledge-empty'));return;}
  let result;try{result=await api(`/sources/${id}/knowledge-units`);}catch{result={items:[],unavailable:true};}
  if(!active()||ticket!==previewRevision)return;
  if(!result.items?.length){preview.append(el('p',result.unavailable?'Available knowledge could not be loaded right now. You can still ask, explore, or use this material in Create.':'Usable knowledge is recorded for this material, but no ideas are available to preview right now. You can still ask a source-grounded question.','muted'));return;}
  const ideas=el('div',undefined,'material-idea-grid');
  for(const group of result.items.slice(0,5)){
   const asset=group.canonical_asset||{},idea=el('article',undefined,'material-idea');idea.append(el('h3',asset.title||'Knowledge idea'));
   if(asset.what_it_says)idea.append(el('p',asset.what_it_says,'material-idea-summary'));
   const evidence=detail('Source & evidence');evidence.className='material-evidence';
   const trail=group.evidence_trail?.length?group.evidence_trail:[{evidence:asset.evidence,chapter_or_section:asset.chapter_or_section}].filter(item=>item.evidence);
   for(const item of trail)evidence.append(el('p',source.title+(item.chapter_or_section?' · '+item.chapter_or_section:''),'muted'),el('blockquote',item.evidence,'evidence'));
   if(!trail.length)evidence.append(el('p','Evidence is not available in this preview.','muted'));
   idea.append(evidence);ideas.append(idea);
  }
  preview.append(ideas);
 }
 function renderPreparation(){
  if(!active())return;
  const outcome=preparationOutcomes.get(id),session=foregroundBuild?.snapshot();
  // A reopened page's fresh server summary wins over a previous in-tab run snapshot.
  if(outcome?.summary&&session?.currentId===id)summary=outcome.summary;
  const running=!!session&&session.status==='running'&&session.currentId===id;
  const category=running?'running':outcome?.category;
  statusTitle.textContent=running?'Preparing':category==='preparation_timeout'||(!category&&summary.attention_category==='build_stopped')?'Preparation paused':['status_unavailable','callback_failure'].includes(category)||summary.readiness==='unknown'?'Status unavailable':summary.readiness==='ready'?'Ready':summary.readiness==='partly_ready'?'Partly ready':summary.readiness==='added'?'Added':summary.readiness==='ready_to_build'?'Ready to prepare':'Preparation not complete';
  coverage.textContent=category==='status_unavailable'?'Preparation progress unavailable':preparationLabel(summary.completed_parts,summary.total_parts);
  progress.hidden=true;progress.max=100;progress.value=summary.total_parts?100*(summary.completed_parts||0)/summary.total_parts:0;progress.setAttribute('aria-valuetext',summary.total_parts?`${Math.round(100*(summary.completed_parts||0)/summary.total_parts)}% prepared`:'Preparation progress unavailable');
  statusNote.textContent=running?(summary.has_usable_knowledge?'Existing knowledge remains available.':''):summary.has_usable_knowledge?'Existing knowledge remains available.':'';
  if(category==='provider_unavailable')statusNote.textContent=summary.has_usable_knowledge?'Existing knowledge remains available.':'Your material remains saved.';
  if(category==='preparation_timeout')statusNote.textContent=summary.has_usable_knowledge?'Your progress is saved. Existing knowledge remains available.':'Your progress is saved.';
  if(!category&&summary.attention_category==='build_stopped')statusNote.textContent=summary.has_usable_knowledge?'Your progress is saved. Existing knowledge remains available.':'Your progress is saved.';
  if(outcome?.interruptionCategory==='provider_rejected')statusNote.textContent='The AI service could not accept this request. Your material and saved work are unchanged.';
  if(outcome?.interruptionCategory==='validation_failed')statusNote.textContent='The response could not be safely checked. Your existing knowledge remains available.';
  if(category==='uncertain')statusNote.textContent='The last request could not be confirmed.';
  if(category==='stopped'||category==='left')statusNote.textContent=summary.has_usable_knowledge?'Existing knowledge remains available.':'Your progress is saved.';
  if(category==='failed')statusNote.textContent=summary.has_usable_knowledge?'Existing knowledge remains available.':'Your material remains saved.';
  if(category==='daily_allowance')statusNote.textContent=summary.has_usable_knowledge?'Existing knowledge remains available.':'Your material remains saved.';
  if(category==='allowance_unavailable')statusNote.textContent='Preparation is unavailable right now. Your material remains saved.';
  if(category==='status_unavailable'||category==='callback_failure')statusNote.textContent='Your confirmed progress is saved. Check the material status before continuing.';
  if(!running&&canPrepare()&&!availableAIAllowance(usage)&&!category){statusTitle.textContent=usage?.daily_limit_reached?'Preparation paused for today.':'Preparation is unavailable right now.';statusNote.textContent='Your material is saved. '+(summary.has_usable_knowledge?'Existing knowledge remains available.':'Preparation can continue when AI is available.');}
  if(summary.operation==='build_unconfirmed'&&!running)statusNote.textContent='The previous preparation request has not reported completion. Check again before continuing.';
  attention.textContent=['provider_unavailable','preparation_timeout','failed','daily_allowance','allowance_unavailable'].includes(category)||(!category&&summary.attention_category==='build_stopped')?'':summary.attention_category?summary.attention_category==='artifact_unavailable'&&summary.has_usable_knowledge?'Source data is unavailable. Existing knowledge remains available. Restore the source data to continue preparing.':summary.attention_category==='build_stopped'?'Preparation paused. Your progress is saved.':summary.attention_category==='build_unconfirmed'?'The previous preparation request has not reported completion.':summary.attention_message||'This material needs attention.':'';
  attention.hidden=!attention.textContent;preparationActions.replaceChildren();
  if(running)statusNote.textContent=summary.has_usable_knowledge?'New knowledge is available as preparation continues.':'New knowledge will appear here as preparation continues.';
  else if(['uncertain','status_unavailable','callback_failure'].includes(category))preparationActions.append(button('Check material status',()=>{preparationOutcomes.delete(id);return navigate('material',{id,replace:true});}));
  else if(canPrepare()){
   const action=button('Continue preparing',()=>startPreparation([id]));action.disabled=!!foregroundBuild||!availableAIAllowance(usage)||['daily_allowance','allowance_unavailable'].includes(category);preparationActions.append(action);
  }
  renderUse();
  if(lastPreviewCount!==summary.completed_parts){lastPreviewCount=summary.completed_parts;loadKnowledge();}
 }
 main.updateMaterialPreparation=renderPreparation;
 main.refreshMaterialStatus=async()=>{if(!active())return;const [freshSummary,freshUsage]=await Promise.all([api(`/sources/${encodeURIComponent(id)}/summary`),api('/usage').catch(()=>null)]);if(!active())return;summary=freshSummary;usage=freshUsage;renderPreparation();};
 const read=async()=>{const task=beginProcessingStatus({label:'Reading your material',detail:'Your original file stays safely attached to this material.'});try{await api(`/sources/${id}/process`,{method:'POST'});announceProcessingStatus('Reading your material is complete.');if(active()&&await navigate('material',{id,replace:true}))await startPreparation([id]);}finally{endProcessingStatus(task);}};
 const uploadFile=async file=>{validateMaterial(file);const task=beginProcessingStatus({label:'Adding your material',detail:'The file is saved before reading begins.'});try{const data=new FormData();data.append('file',file);await api(`/sources/${id}/upload`,{method:'POST',body:data});await read();}finally{endProcessingStatus(task);}};
 const needsUpload=!source.file_path||['unattached','missing'].includes(summary.file_state)||['ocr_required','unsupported_extraction'].includes(summary.attention_category);
 if(needsUpload&&summary.file_replacement_allowed){
  const upload=form(async fd=>uploadFile(fd.get('file'))),[label,input]=field(summary.attention_category==='ocr_required'?'Choose a different file with selectable text':'Choose a supported file','file');input.type='file';input.accept=MATERIAL_EXTENSIONS.join(',');input.required=true;
  const action=submit(summary.file_state==='available'?'Use replacement file':'Upload file');requireValidFile(input,action);upload.append(label,action);rail.append(upload);
 }else if(summary.file_state==='available'&&['read_source'].includes(summary.next_action))rail.append(button('Read and prepare material',read,'primary'));
 const eligible=summary.recovery?.filter(item=>item.allowed&&(summary.operation==='build_unconfirmed'?item.category==='unconfirmed_build':!canPrepare()))||[];
 if(eligible.length){const recovery=el('section',undefined,'material-recovery');recovery.append(el('h2','Resume preparation safely'),el('p','Resolve the interrupted attempt first. Preparation will only continue when you choose Continue preparing.','muted'),button('Resolve preparation issue',async()=>{for(const item of eligible)await api(`/knowledge-extractions/${encodeURIComponent(item.job_id)}/recover`,{method:'POST'});if(active())await navigate('material',{id,replace:true});}));rail.append(recovery);}
 const manage=detail('Manage material');manage.className='material-manage';
 if(libraryName)manage.append(el('p',`In ${libraryName}`,'muted'));
 if(source.file_name)manage.append(el('p',`Original file: ${source.file_name}${source.file_type?` · ${source.file_type.replace('.','').toUpperCase()}`:''}`,'muted'));
 if(source.file_path){const original=el('a','Open original file');original.href=`/sources/${encodeURIComponent(id)}/file`;original.target='_blank';original.rel='noopener';manage.append(original);}
 if(source.file_path&&summary.file_replacement_allowed){
  const replacement=detail('Replace original file',el('p','Replacing the file keeps this material record and rereads the replacement.','muted'));
  const replacementForm=form(async fd=>uploadFile(fd.get('file')));
  const [label,input]=field('Choose a supported file','file');input.type='file';input.accept=MATERIAL_EXTENSIONS.join(',');input.required=true;
  const action=submit('Use replacement file');requireValidFile(input,action);
  replacementForm.append(label,action);replacement.append(replacementForm);manage.append(replacement);
 }else if(source.file_path&&!summary.file_replacement_allowed)manage.append(el('p','The original file can’t be replaced after preparation has started. Add another material to use a different file.','muted'));
 manage.append(button('Delete material',async()=>{
  if(!confirm('Delete this material, its original file, its knowledge, and saved work histories that use its knowledge? This cannot be undone.'))return;
  await api(`/sources/${encodeURIComponent(id)}?delete_outputs=true`,{method:'DELETE'});
  if(!active())return;state.selected.clear();state.source=null;
  if(await navigate('library',{replace:true}))message('Material and related saved work were deleted.');
 },'danger'));
 workspace.append(manage);


 renderPreparation();
}
async function developerSourceView(id){
 const active=beginView();heading('INTERNAL · SUPPORT','Material diagnostics','Technical tools for the workspace owner or developer.');
 const [source,summary]=await Promise.all([api(`/sources/${id}`),api(`/sources/${id}/summary`)]);if(!active())return;
 main.append(button('Back to material',()=>navigate('material',{id})));
 if(source.chunks_path&&Number.isInteger(summary.total_parts)&&summary.total_parts>0){
 const advanced=detail('Advanced / Developer');advanced.className='material-advanced';main.append(advanced);
 const advancedStatus=el('p','Developer details have not been loaded.','muted');advanced.append(advancedStatus);
 let diagnosticsLoaded=false,diagnosticsLoading=false;
 advanced.ontoggle=()=>{
  if(!advanced.open||diagnosticsLoaded||diagnosticsLoading)return;
  diagnosticsLoading=true;
  advancedStatus.textContent='Loading developer details…';
  return run(async()=>{
   try{
    const [audit,chunks]=await Promise.all([api(`/sources/${id}/audit`),source.chunks_path?api(`/sources/${id}/chunks`):Promise.resolve({items:[]})]);
    if(!active())return;
    const diagnostics=el('section',undefined,'developer-diagnostics');diagnostics.append(el('h2','Source diagnostics'));
    diagnostics.append(list([`Internal source ID: ${source.id}`,`Read state: ${summary.read_state}`,`Operation: ${summary.operation}`,`Overlap: ${Math.round((audit.overlap_rate||0)*100)}%`,`Superseded knowledge records: ${audit.superseded_assets.length}`,`Older schema records: ${audit.old_schema_assets.length}`,`Missing evidence: ${audit.missing_evidence.length}`,`Evidence needing review: ${audit.evidence_needing_review.length}`,`Confidence distribution: ${JSON.stringify(audit.confidence_distribution)}`]));
    diagnostics.append(el('p',audit.note||'Audit details are diagnostic and do not indicate source quality.','muted'));
    if(audit.jobs?.length){diagnostics.append(el('h3','Build history'));diagnostics.append(list(audit.jobs.map(job=>`${job.id} · ${job.chunk_id} · ${job.status}${job.error?` · ${job.error}`:''}`)));}
    if(chunks.items?.length){diagnostics.append(el('h3','Processing parts'));diagnostics.append(list(chunks.items.map(chunk=>`${chunk.id} · Part ${chunk.chunk_index} · ${chunk.word_count} words${chunk.chapter_or_section?` · ${chunk.chapter_or_section}`:''}`)));}
    if(source.chunks_path){
     const manual=form(async fd=>{
      const chunkId=fd.get('Processing part');
      const job=(await api('/knowledge-extractions',{method:'POST',body:{source_id:id,chunk_id:chunkId,reprocess:fd.get('replace')==='on'}})).job;
      const raw=fd.get('result').trim();
      if(raw){let parsed;try{parsed=JSON.parse(raw);}catch{throw new Error('Paste valid extraction JSON with an assets array.');}await api(`/knowledge-extractions/${job.id}/results`,{method:'POST',body:parsed});if(active()&&await navigate('material',{id,replace:true}))message('Knowledge imported and validated.');}
      else{const request=await api(`/knowledge-extractions/${job.id}/request`);download(`${job.id}-prompt.json`,JSON.stringify(request,null,2),'application/json');message('Prompt downloaded for manual knowledge import.');}
     });
     const [chunkLabel,chunkSelect]=select('Processing part',chunks.items.map(chunk=>[chunk.id,`Part ${chunk.chunk_index} · ${chunk.word_count} words${chunk.chapter_or_section?` · ${chunk.chapter_or_section}`:''}`]));manual.append(chunkLabel);
     const [resultLabel,resultInput]=field('Structured knowledge result (leave empty to download a prompt)','result','textarea');manual.append(resultLabel);
     const [replaceLabel,replaceInput]=field('Intentionally replace this part’s active knowledge','replace');replaceInput.type='checkbox';replaceLabel.className='check';manual.append(replaceLabel,submit('Download prompt / import result'));
     diagnostics.append(el('h3','Manual knowledge import'));diagnostics.append(manual);
    }
    advancedStatus.remove();advanced.append(diagnostics);diagnosticsLoaded=true;
   }catch(error){if(active()){advancedStatus.textContent='No developer details are available for this material right now.';message('Advanced diagnostics could not be loaded. Material knowledge and actions remain available.',true);}}
   finally{diagnosticsLoading=false;}
  });
 };
 }
}

function download(name,text,type='text/plain'){const a=el('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function knowledgeView(){const active=beginView();
 heading('LIBRARY / ASK & EXPLORE','Ideas you can put to work.',explorePicker?'Choose ideas for your Create draft, or explore your materials.':'Find useful ideas or ask a grounded question about your materials.');
 exploreState ||= freshExplore();const local=exploreState;main.exploreContext={state:local,sourceIds:()=>s.value?[s.value]:sources.map(item=>item.id),sourceInfo:()=>sources.map(({id,title,author})=>({id,title,author})),scopeLabel:()=>s.value?[sources.find(item=>item.id===s.value)?.title||'the selected material',sources.find(item=>item.id===s.value)?.author].filter(Boolean).join(' · '):broadScope,handoff:(request,sourceIds)=>openCreate({request,materials:sourceIds,library:state.library,selectedIds:[...state.selected],outputType:'knowledge_answer'})};
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
 search.id='ke-search-form';qi.id='explore-request';qi.rows=3;const captureActions=actions(submit('Find matching ideas'));captureActions.id='explore-actions';search.append(l,ql,captureActions);main.append(search);
 const searchPanel=el('section');searchPanel.hidden=true;searchPanel.id='ke-search-results';searchPanel.setAttribute('aria-live','polite');
 const searchHeading=query=>query.trim().length>64||query.includes('\n')?'Related ideas':`Search results for “${query}”`;
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
 searchPanel.append(el('h2',status==='loading'?'Searching…':status==='error'?'Search could not be completed':searchHeading(query)));
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
 if(local.results){const grid=el('div',undefined,'grid');searchPanel.hidden=false;searchPanel.append(el('h2',searchHeading(local.results.query)),grid);cards(grid,local.results.groups);}
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
   const processing=beginProcessingStatus({label:'Creating your draft',detail:'Your confirmed request and selected knowledge are being used.'});
   let r;try{r=await api('/workshops/generate',{method:'POST',body:payload});}catch(error){
     if(!active()||ticket!==actionRevision)return;
     interactionDraft={...interactionDraft,prepared:null,confirmation:{state:'unconfirmed',snapshot:null}};
     showStale('Knowledge needs an update before another Create attempt.');throw error;
   }finally{endProcessingStatus(processing);}
   if(!active()||ticket!==actionRevision||identity!==evidenceIdentity(interactionDraft,workshopRequest(interactionDraft,catalog())))return;
   if(!await navigate('work',{id:r.saved_output.id}))return;
   announceProcessingStatus('Your draft was created and saved.');
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
     coverage.append(el('p',source.title+' · '+(known?preparationLabel(source.prepared_sections,source.total_sections):'Preparation progress unavailable')+(source.relevant_idea_count?` · ${source.relevant_idea_count} relevant ${source.relevant_idea_count===1?'idea':'ideas'}`:'')));
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
   preview.replaceChildren(el('p','Your knowledge preview will appear here.','muted'));
   const processing=beginProcessingStatus({label:'Searching your knowledge',detail:'Finding material that fits your request.'});
   try{
     const r=await api('/workshops/prepare',{method:'POST',body:payload});
     if(!active()||ticket!==actionRevision||identity!==evidenceIdentity(interactionDraft,payload))return;
     if(!r.prepared_snapshot_id||r.interaction_revision!==interactionDraft.revision)throw Error('Knowledge preview could not be confirmed. Update knowledge before creating.');
     interactionDraft={...interactionDraft,prepared:{identity,revision:interactionDraft.revision,evidence:r}};renderPreview(r);announceProcessingStatus('Relevant knowledge is ready to review.');
   }catch(error){if(!active()||ticket!==actionRevision)return;showStale('Knowledge could not be updated. Your request and corrections are kept.');throw error;}finally{endProcessingStatus(processing);}
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
async function outputView(id){
 const active=beginView();heading('MY WORK','Opening work…','');const o=await api(`/outputs/${id}`);if(!active())return;const quality=await api(`/outputs/${id}/quality`);if(!active())return;
 let sourceTitles=new Map(),sourceInfo=[];try{const sourceData=await api('/sources');if(!active())return;sourceInfo=(sourceData.items||[]).map(({id,title,author})=>({id,title,author}));sourceTitles=new Map(sourceInfo.map(source=>[source.id,source.title]).filter(([,title])=>Boolean(title)));}catch{/* Saved work remains reviewable if material titles are unavailable. */}
 heading('VERSION '+o.version,o.title,`${o.output_type.replaceAll('_',' ')} · Saved ${new Date(o.created_at).toLocaleString()}`);
 const review=card('Quality review',quality.validation_status.replaceAll('_',' '));review.append(el('p',o.provider==='manual'?'Manually supplied or edited':'Created with AI'),el('p',quality.note),list(quality.issues.map(i=>i.message)));if(quality.timing_checks)review.append(list(quality.timing_checks.map(c=>`${c.criterion.replaceAll('_',' ')}: ${c.status} · Requested: ${c.requested_minutes??'unknown'} min · Calculated: ${c.calculated_minutes??'unknown'} min`)));
 const exportLink=el('a','Export Markdown');exportLink.href=`/outputs/${id}/export`;const reading=renderGroundedAnswer(o.content,{document,snapshot:o.knowledge_snapshot||[],sourceInfo});reading.className=`${reading.className||''} reading`.trim();main.append(actions(button('← My work',()=>navigate('outputs')),exportLink),reading);const answerTableObserver=observeAnswerTableOverflow(reading);main._answerTableObserver?.disconnect();main._answerTableObserver=answerTableObserver;
 const evidence=detail('Ideas and evidence used');main.append(evidence);for(const ref of o.applied_knowledge||[]){const g=(o.knowledge_snapshot||[]).find(item=>item.canonical_asset?.id===ref.asset_id);const c=card(g?.canonical_asset?.title||'Knowledge used',ref.usage_note);const evidenceItems=(g?.evidence_trail||[]).map(item=>{const sourceTitle=sourceTitles.get(item.source_id);const context=[sourceTitle,item.chapter_or_section].filter(Boolean).join(' · ');return el('p',(context?context+'\n':'')+item.evidence,'evidence');});if(evidenceItems.length)c.append(detail('Source & evidence',...evidenceItems));evidence.append(c);}
 main.append(detail('Review and design choices',review,list(o.design_choices.length?o.design_choices:['No additional design choices recorded.'])));
 const revise=form(async fd=>{const body=revisionPayload(fd,o),processing=beginProcessingStatus({label:body.manual?'Saving changes':'Revising your work',detail:body.manual?'Your manual edits will be saved as a new version.':'The requested AI revision is being prepared.'});let n;try{n=await api(`/outputs/${id}/revise`,{method:'POST',body});}finally{endProcessingStatus(processing);}if(!active())return;if(!await navigate('work',{id:n.id}))return;announceProcessingStatus(body.manual?'Your manual edits were saved as a new version.':'Your revised work was saved as a new version.');message(`Saved version ${n.version}; the original is unchanged.`);});
 const [il,ii]=field('Revision instruction','instruction');ii.required=true;ii.minLength=2;const [ml,mi]=field('Save my manual edits','manual');mi.type='checkbox';mi.checked=true;ml.className='check';
 const revisionMode=el('p','No AI used. Your edits will be saved as a new version.','muted');const [tl,ti]=field('Title','title','input',o.title),[cl,ci]=field('Edited content','content','textarea',o.content),[dl,di]=field('Design choices — one per line','choices','textarea',o.design_choices.join('\n'));ci.rows=12;
 const revisionSubmit=submit('Save manual edits');mi.onchange=()=>{revisionSubmit.textContent=mi.checked?'Save manual edits':'Revise with AI';revisionMode.textContent=mi.checked?'No AI used. Your edits will be saved as a new version.':'This sends one explicit AI revision request.';};
 revise.append(il,ml,revisionMode,tl,cl,dl,revisionSubmit);main.append(detail('Revise this work',revise));
 const history=await api(`/outputs/${id}/history`);if(!active())return;const h=card('Version history');const diff=el('pre');for(const v of history.items)h.append(actions(button(`Open version ${v.version}`,()=>navigate('work',{id:v.id})),v.id!==id?button(`Compare v${o.version} → v${v.version}`,async()=>{const r=await api(`/outputs/${id}/compare/${v.id}`);diff.textContent=`Changed: ${r.changed_fields.join(', ')||'None'}\n\n${r.content_diff}`;}):el('span','Current','badge')));h.append(diff);main.append(h,actions(button('Delete work and version history',async()=>{if(!confirm('Delete this work and every revision? This cannot be undone.'))return;await api(`/outputs/${id}?entire_history=true`,{method:'DELETE'});if(!active())return;await navigate('outputs',{replace:true});},'danger')));
}
async function settingsView(){const active=beginView();heading('SETTINGS','Your data, in your hands.','Keep backups private: they contain your materials and saved work.');const [usage,integrity]=await Promise.all([api('/usage'),api('/data/integrity')]);if(!active())return;const remaining=Math.max(0,usage.daily_call_limit-usage.calls_today);const aiState=!usage.configured?'AI unavailable':!usage.free_tier_confirmed?'AI unavailable':usage.paused?'AI temporarily paused':'Available for explicit requests';const freeTierNote=usage.free_tier_confirmed?'This workspace is configured to stay within the approved $0 beta policy.':'AI is unavailable until the workspace owner confirms the approved $0 beta policy.';const c=card('Shared beta allowance');c.append(el('p',`Shared allowance used today: ${usage.calls_today} of ${usage.daily_call_limit}`),el('p',`Shared allowance remaining today: ${remaining}`),el('p','This allowance is shared across the workspace. AI is unavailable once today’s allowance is used.','muted'),el('p','Searching, browsing, reading material and editing requests do not use this allowance.','muted'),el('p',freeTierNote,'muted'),el('p',`AI status: ${aiState}`,'muted'));if(usage.paused&&!usage.daily_limit_reached)c.append(button('Resume after quota reset',async()=>{await api('/usage/resume',{method:'POST'});if(!active())return;await navigate('settings',{replace:true});}));const e=el('a','Download complete private backup');e.href='/data/export';const data=card('Export & integrity',integrity.ok?'No broken record links or missing material files detected.':`${integrity.issues.length} integrity issue(s) require attention.`);data.append(e,integrity.issues.length?el('p','Some saved material information needs attention. Contact the workspace owner.','muted'):el('p',''));main.append(c,data);if(csrfToken()){logoutButton.hidden=false;main.append(logoutButton);}}
const views={home:homeView,library:libraryView,knowledge:knowledgeView,workshop:workshopView,outputs:savedView,settings:settingsView,material:sourceView,developerMaterial:developerSourceView,work:outputView};
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
window.addEventListener('pagehide',()=>{foregroundBuild?.stop('navigation');captureDraft();});
router.start();
