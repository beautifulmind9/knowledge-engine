import {MATERIAL_EXTENSIONS, validateMaterial, suggestedMaterialTitle, newMaterialAdd, addMaterial} from './material-add.js';
import { revisionPayload } from './output-revision.js';
import {api, apiFetch, csrfToken} from './api.js';
import {createNavigation} from './navigation.js';
import {newInteractionDraft, captureRequest, correctDraft, interpretDraft, draftNeedsInterpretation, workshopRequest, evidenceIdentity, confirmDraft, preparedGenerationRequest} from './interaction-draft.js';
import { PAGE_SIZE, filterUnits, createSearchController } from './knowledge-browser.js';
const main=document.querySelector('main'), feedback=document.querySelector('#feedback');
let interactionDraft=newInteractionDraft(),createMaterials=null,viewRevision=0;
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
async function run(fn,b){if(b)b.disabled=true;main.setAttribute('aria-busy','true');message('Working…');let revision=viewRevision;try{const pending=fn();revision=viewRevision;await pending;if(revision!==viewRevision)return;if(feedback.textContent==='Working…')message('');}catch(e){if(revision===viewRevision)message(e.message,true);}finally{if(b)b.disabled=false;if(revision===viewRevision)main.removeAttribute('aria-busy');}}
function field(label,name,kind='input',value=''){const l=el('label',label),i=el(kind);i.name=name;if(kind==='textarea')i.rows=4;i.value=value;l.append(i);return [l,i];}
function select(label,values,current='',multiple=false){const [l,s]=field(label,label,'select');s.multiple=multiple;for(const [id,name] of values){const o=el('option',name);o.value=id;o.selected=Array.isArray(current)?current.includes(id):id===current;s.append(o);}return [l,s];}
function form(onSubmit){const f=el('form');f.onsubmit=e=>{e.preventDefault();return run(()=>onSubmit(new FormData(f)),f.querySelector('[type=submit]'));};return f;}
function submit(text){const b=el('button',text,'primary');b.type='submit';return b;}
function heading(kicker,title,description){main.captureExplore=null;main.exploreContext=null;main.refreshMaterialAdd=null;const signout=main.querySelector('#beta-logout');if(signout){signout.hidden=true;document.body.append(signout);}main.replaceChildren(el('div',kicker,'kicker'),el('h1',title),el('p',description,'intro'));}
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
const libraryReadiness={added:'Added',ready_to_build:'Ready to build knowledge',partly_ready:'Partly ready',ready:'Ready',unknown:'Status unavailable'};
function rowAction(summary){
 if(!summary)return 'Open material';
 if(summary.has_usable_knowledge)return 'Explore knowledge';
 if(summary.attention_category==='build_stopped'||summary.attention_category==='build_unconfirmed'||summary.recovery?.some(item=>item.allowed))return 'Open material';
 if(summary.readiness==='added'&&summary.next_action==='attach_file')return 'Finish adding';
 if(summary.readiness==='added'&&summary.next_action==='read_source')return 'Read source';
 if(summary.readiness==='ready_to_build'&&summary.next_action==='build_knowledge')return 'Build knowledge';
 if(summary.readiness==='partly_ready'&&summary.next_action==='continue_building')return 'Continue building';
 return 'Open material';
}
function renderLibraryRow(source,summary,summaryUnavailable=false){
 const row=el('article',undefined,'library-row');
 const title=el('h2',source.title,'library-row-title');row.append(title);
 if(source.author?.trim())row.append(el('p',source.author,'library-row-author'));
 const action=rowAction(summary);
 if(action!=='Open material'){const open=el('a','Open material','library-row-open');open.href='#/library/material/'+encodeURIComponent(source.id);open.onclick=event=>{event.preventDefault();return run(()=>navigate('material',{id:source.id}));};row.append(open);}
 if(summary){
  row.append(el('p',libraryReadiness[summary.readiness]||'Status unavailable','library-row-readiness'));
  const coverage=summary.coverage_text||(summary.readiness==='unknown'?'Coverage unavailable':summary.readiness==='added'&&summary.total_parts===0?'No parts ready yet':'Coverage unavailable');
  row.append(el('p',coverage,'library-row-coverage'));
  if(summary.readiness==='ready'&&!summary.has_usable_knowledge)row.append(el('p','No usable knowledge is available from this material yet.','library-row-operation'));
  if(summary.attention_category)row.append(el('p',`Needs attention: ${summary.attention_message||'This material needs attention.'}`,'library-row-attention'));
  if(summary.operation==='build_unconfirmed'&&summary.attention_category!=='build_unconfirmed')row.append(el('p','Previous build has not reported completion.','library-row-operation'));
 }else{
  row.append(el('p',summaryUnavailable?'Readiness unavailable':'Status unavailable','library-row-readiness'));
  row.append(el('p','Coverage unavailable','library-row-coverage'));
  if(summaryUnavailable)row.append(el('p','Current status could not be loaded. Open the material to check it.','library-row-operation'));
 }
 const controls=actions();
 controls.append(button(action,async()=>{
  if(action==='Explore knowledge')return navigate('knowledge',{library:source.library_id||state.library,materials:[source.id],source:source.id,exploreState:freshExplore(exploreState?.query||'')});
  if(action==='Finish adding'||action==='Open material')return navigate('material',{id:source.id});
  if(action==='Read source'){
   await api(`/sources/${source.id}/process`,{method:'POST'});
   if(!await navigate('library',{replace:true}))return;
   message('Source read. Build knowledge to find ideas you can use.');return;
  }
  const result=await api(`/sources/${source.id}/interpret?max_chunks=1`,{method:'POST'});
  if(!await navigate('library',{replace:true}))return;
  message(result.stopped_reason?'Knowledge building stopped.':`${result.processed_this_run||1} part ready.`,!!result.stopped_reason);
 },'primary'));
 row.append(controls);return row;
}
async function homeView(){beginView();heading('HOME','What would you like to do?','What are you trying to learn, decide, make, plan or figure out?');
 const entry=el('section',undefined,'home-intent'),[label,input]=field('Your request','home_request','textarea',homeDraft.originalRequest);input.rows=3;input.placeholder='Start with what’s on your mind.';
 input.oninput=()=>{main.querySelector('#create-handoff')?.remove();homeDraft=captureRequest(homeDraft,input.value);};
 entry.append(label,actions(button('Ask & Explore',()=>navigate('knowledge',{library:null,materials:[],source:null,exploreState:freshExplore(input.value)})),button('Create something',()=>input.value.trim()?openCreate({request:input.value,materials:[],selectedIds:[]}):openCreate())),el('p','Choose what you’d like to do with your request.','muted'));main.append(entry);
 const choices=el('div',undefined,'home-choices');for(const [title,description,view] of [['Add to my library','Bring in material you want to use.','library'],['Continue my work','Return to something created earlier.','outputs']]){const row=el('section');row.append(button(title,()=>navigate(view,view==='library'?{add:true}:{})),el('p',description));choices.append(row);}main.append(choices);}
function materialAddSurface(libs,active){
 if(!materialAddDraft?.file&&!materialAddDraft?.sourceId)materialAddDraft=newMaterialAdd(libs,state.library);
 const draft=materialAddDraft;
 const surface=card('Add material','PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON · up to 25 MiB');surface.id='material-add';
 const [fileLabel,fileInput]=field('Choose material file','file');fileInput.type='file';fileInput.accept=MATERIAL_EXTENSIONS.join(',');
 const confirmation=el('div');confirmation.id='material-confirmation';
 surface.append(fileLabel,confirmation);
 function renderConfirmation(){
  confirmation.replaceChildren();if(draft.libraryId&&!libs.some(l=>l.id===draft.libraryId))libs.push({id:draft.libraryId,name:draft.libraryName});if(draft.sourceId){const empty=main.querySelector('#library-empty');if(empty)empty.textContent=draft.read?'Material is ready to build knowledge. Open it above.':'Material addition is incomplete. Resume above or open the saved material.';}fileInput.disabled=draft.busy||!!draft.sourceId;
  if(!draft.file)return;
  confirmation.append(el('h3','Here’s what we found'),el('p',`${draft.file.name} · ${draft.file.name.split('.').at(-1).toUpperCase()} · ${draft.file.size<1024?draft.file.size+' bytes':draft.file.size<1024*1024?(draft.file.size/1024).toFixed(1)+' KiB':(draft.file.size/1024/1024).toFixed(2)+' MiB'}`,'file-facts'));
  const [titleLabel,title]=field('Title · suggested from filename','title','input',draft.title);title.required=true;title.maxLength=500;title.disabled=draft.busy||!!draft.sourceId;title.oninput=()=>{draft.title=title.value;};confirmation.append(titleLabel);
  const destinationName=libs.find(l=>l.id===draft.libraryId)?.name||draft.libraryName;
  const destination=el('p',`Destination · ${destinationName}`);confirmation.append(destination);
  if(!draft.sourceId){
   const change=detail('Change destination');
   if(libs.length){const [label,selectInput]=select('Destination',[...libs.map(l=>[l.id,l.name]),['','New library']],draft.libraryId||'');selectInput.setAttribute('aria-label','Destination');change.append(label);selectInput.disabled=draft.busy;selectInput.onchange=()=>{draft.libraryId=selectInput.value||null;nameLabel.hidden=!!draft.libraryId;destination.textContent='Destination · '+(libs.find(l=>l.id===draft.libraryId)?.name||draft.libraryName);};}
   const [nameLabel,name]=field('New library name','destination_name','input',draft.libraryName);name.required=true;name.maxLength=200;name.disabled=draft.busy;nameLabel.hidden=!!draft.libraryId;name.oninput=()=>{draft.libraryName=name.value;destination.textContent='Destination · '+name.value;};change.append(nameLabel);confirmation.append(change);
   const [authorLabel,author]=field('Author / creator (optional)','author','input',draft.author);author.disabled=draft.busy;author.oninput=()=>{draft.author=author.value;};confirmation.append(detail('Optional details',authorLabel));
  }
  if(draft.error){const error=el('p',draft.error.message,'error');error.setAttribute('role','alert');confirmation.append(error);}
  const needsDifferentFile=draft.uploaded&&draft.readFailure==='ocr_required';
  const retryLabel=needsDifferentFile?'Choose a different file':draft.replacementSelected?'Use replacement file':draft.read?'Open material':draft.uploaded?'Retry reading':draft.sourceId?'Retry upload':draft.error?'Retry Add material':'Add material';
  const add=button(retryLabel,async()=>{
   if(needsDifferentFile){confirmation.querySelector('[name=replacement_file]')?.click();return;}
   if(!title.reportValidity())return;
   const pending=addMaterial(draft,api,file=>{const data=new FormData();data.append('file',file);return data;},text=>{if(active())message(text);});
   renderConfirmation();
   try{if(!await pending)return;if(!active())return;materialAddDraft=null;await navigate('material',{id:draft.sourceId,library:draft.libraryId});}
   catch(error){if(active())renderConfirmation();throw error;}
   finally{main.refreshMaterialAdd?.();}
  },'primary');add.disabled=draft.busy;
  const controls=actions(add);
  if(draft.sourceId&&!draft.read)controls.append(button('Open material',()=>navigate('material',{id:draft.sourceId,library:draft.libraryId})));
  else if(!draft.sourceId){const cancel=button('Cancel',()=>{draft.file=null;draft.error=null;fileInput.value='';renderConfirmation();});cancel.disabled=draft.busy;controls.append(cancel);}
  confirmation.append(controls);
  if(draft.sourceId&&!draft.read){const [label,replacement]=field(needsDifferentFile?'Choose a different file with selectable text':'Choose a replacement file','replacement_file');replacement.type='file';replacement.disabled=draft.busy;replacement.accept=MATERIAL_EXTENSIONS.join(',');replacement.onchange=()=>{try{validateMaterial(replacement.files?.[0]);draft.file=replacement.files[0];draft.uploaded=false;draft.readFailure=null;draft.replacementSelected=true;draft.error=null;renderConfirmation();}catch(error){message(error.message,true);}};confirmation.append(label);}
 }
 fileInput.onchange=()=>{try{const file=fileInput.files?.[0];validateMaterial(file);draft.file=file;draft.title=suggestedMaterialTitle(file.name);draft.error=null;renderConfirmation();message('');}catch(error){draft.file=null;renderConfirmation();message(error.message,true);}};
 main.refreshMaterialAdd=renderConfirmation;renderConfirmation();return surface;
}
async function libraryView(_id,route={}){const active=beginView();heading('LIBRARY','Your library','Add material, find useful ideas, and bring them into your work.');const libs=await libraries();if(!active())return;
 if(libs.length>1){const [l,s]=select('Filter by library',[['','All libraries'],...libs.map(l=>[l.id,l.name])],state.library||'');s.onchange=()=>{state.library=s.value||null;state.source=null;state.selected.clear();if(!materialAddDraft?.file)materialAddDraft=null;run(()=>navigate('library',{replace:true}));};main.append(l);}
 const sources=libs.length?await sourceItems():[];if(!active())return;
 let summaries=[],summaryUnavailable=false;
 if(sources.length){try{summaries=await api('/sources/summaries'+(state.library?'?library_id='+encodeURIComponent(state.library):''));}catch{summaryUnavailable=true;}}
 if(!active())return;
 const summaryById=new Map(summaries.map(summary=>[summary.source_id,summary]));
 const addDetails=detail('Add material',materialAddSurface(libs,active));addDetails.className='library-add';addDetails.open=route.add||!sources.length||!!materialAddDraft?.file;main.append(addDetails);
 if(!sources.length){const empty=el('p','Choose a file to add material to your library. You can organize it into libraries later.','empty');empty.id='library-empty';main.append(empty);}
 main.append(actions(button('Ask & Explore',()=>navigate('knowledge',{materials:[],source:null}),sources.length?'':'secondary')));
 const create=form(async fd=>{const lib=await api('/libraries',{method:'POST',body:{name:fd.get('name'),description:fd.get('description')}});if(!active())return;state.library=lib.id;if(!materialAddDraft?.file)materialAddDraft=null;if(!await navigate('library',{add:true,replace:true}))return;message('Library created.');});for(const [label,name] of [['Library name','name'],['Description','description']]){const [l,i]=field(label,name);i.required=name==='name';create.append(l);}create.append(submit('Create library'));main.append(detail('Create a library',create));
 const grid=el('div',undefined,'library-rows');for(const source of sources)grid.append(renderLibraryRow(source,summaryById.get(source.id),summaryUnavailable));main.append(grid);
}
async function sourceView(id){
 const active=beginView(),previousSource=state.source;
 state.source=id;
 heading('LIBRARY · MATERIAL','Opening material…','');
 const [source,summary,libraryData]=await Promise.all([api(`/sources/${id}`),api(`/sources/${id}/summary`),libraries()]);
 if(!active())return;
 if(materialAddDraft?.sourceId===id){materialAddDraft.uploaded=!!source.file_path;materialAddDraft.read=summary.read_state==='read';materialAddDraft.readFailure=summary.attention_category;}
 const readinessLabels={added:'Added',ready_to_build:'Ready to build knowledge',partly_ready:'Partly ready',ready:'Ready',unknown:'Status unavailable'};
 heading('LIBRARY · MATERIAL',source.title,source.author||'');
 const libraryName=libraryData.find(item=>item.id===source.library_id)?.name||null;
 const back=button('← Library',()=>navigate('library'));
 main.append(actions(back));

 const status=card('Material status',readinessLabels[summary.readiness]||'Status unavailable');status.className='card material-status';
 status.append(el('p',summary.coverage_text||(summary.readiness==='added'?'No parts ready yet':'Coverage unavailable'),'material-coverage'));
 if(summary.operation==='build_unconfirmed'&&summary.attention_category!=='build_unconfirmed')status.append(el('p','Previous build has not reported completion.','material-operation'));
 if(summary.attention_category){const attentionMessage=summary.attention_category==='artifact_unavailable'&&summary.has_usable_knowledge?'Source data is unavailable. Existing knowledge remains available. Restore the source data to continue building knowledge.':summary.attention_message||'This material needs attention.';status.append(el('p',`Needs attention: ${attentionMessage}`,'material-attention'));}
 main.append(status);

 const sameSourceContext=previousSource===id&&createMaterials?.includes(id);
 const selectedForSource=sameSourceContext?[...state.selected]:[];
 const openScopedKnowledge=(query='')=>navigate('knowledge',{
  source:id,materials:[id],library:source.library_id||null,
  exploreState:sameSourceContext&&exploreState?exploreState:freshExplore(query),
  selectedIds:selectedForSource,
 });
 const build=async()=>{
  message('Building knowledge…');
  const result=await api(`/sources/${id}/interpret?max_chunks=1`,{method:'POST'});
  if(!active()||!await navigate('material',{id,replace:true}))return;
  message(result.stopped_reason?'Knowledge building stopped. Check the material status for details.':`${result.processed_this_run||1} part ready.`,!!result.stopped_reason);
 };
 const read=async()=>{
  message('Reading source…');await api(`/sources/${id}/process`,{method:'POST'});
  if(!active()||!await navigate('material',{id,replace:true}))return;
  message('Source read. Choose Build knowledge when you are ready.');
 };
 const uploadFile=async file=>{
  validateMaterial(file);
  const data=new FormData();data.append('file',file);
  await api(`/sources/${id}/upload`,{method:'POST',body:data});
  if(materialAddDraft?.sourceId===id)materialAddDraft.uploaded=true;
  message('Reading source…');await api(`/sources/${id}/process`,{method:'POST'});
  if(!active()||!await navigate('material',{id,replace:true}))return;
  message('Source read. Choose Build knowledge when you are ready.');
 };
 const uploadLabel=summary.attention_category==='ocr_required'?'Choose a different file with selectable text':summary.attention_category==='unsupported_extraction'?'Choose a supported file':'Choose a file';
 const canRetryRead=summary.file_state==='available'&&!!source.file_path&&!source.chunks_path&&summary.read_state==='read_failed';
 const noParts=summary.readiness==='ready_to_build'&&!summary.has_usable_knowledge;
 const needsUpload=!source.file_path||summary.file_state==='unattached'||summary.file_state==='missing'||summary.attention_category==='ocr_required'||summary.attention_category==='unsupported_extraction';
 const canOfferUpload=needsUpload&&summary.file_replacement_allowed;
 let primary=null;
 if(canOfferUpload){
  const uploadForm=form(async fd=>uploadFile(fd.get('file')));
  const [label,input]=field(uploadLabel,'file');input.type='file';input.accept=MATERIAL_EXTENSIONS.join(',');input.required=true;
  const action=submit(summary.attention_category==='ocr_required'||summary.file_state==='available'?'Use replacement file':'Upload file');requireValidFile(input,action);
  uploadForm.append(label,action);
  primary=el('section',undefined,'material-primary material-upload');primary.append(el('h2','What you can do now'),uploadForm);main.append(primary);
 }else if(canRetryRead||summary.next_action==='read_source'&&summary.file_state==='available'){
  primary=el('section',undefined,'material-primary');primary.append(el('h2','What you can do now'),button('Read source',read,'primary'));main.append(primary);
 }else if(noParts&&summary.next_action==='build_knowledge'){
  primary=el('section',undefined,'material-primary');primary.append(el('h2','What you can do now'),button('Build knowledge',build,'primary'));main.append(primary);
 }else if(summary.readiness==='partly_ready'&&!summary.has_usable_knowledge&&summary.next_action==='continue_building'){
  primary=el('section',undefined,'material-primary');primary.append(el('h2','What you can do now'),button('Continue building',build,'primary'));main.append(primary);
 }else if(summary.has_usable_knowledge){
  primary=el('section',undefined,'material-primary');primary.append(el('h2','What you can do now'),button('Ask this source',()=>openScopedKnowledge('What does this material teach?'),'primary'));main.append(primary);
 }else if(summary.readiness==='ready'){
  status.append(el('p','No usable knowledge is available from this material yet.','material-empty-knowledge'));
  if(source.file_path){primary=el('section',undefined,'material-primary');primary.append(el('h2','What you can do now'),button('Open original file',()=>window.open(`/sources/${encodeURIComponent(id)}/file`,'_blank','noopener'),'primary'));main.append(primary);}
 }else if(summary.readiness==='unknown'&&summary.file_state==='available'&&source.file_path){
  primary=el('section',undefined,'material-primary');primary.append(el('h2','What you can do now'),button('Open original file',()=>window.open(`/sources/${encodeURIComponent(id)}/file`,'_blank','noopener'),'primary'));main.append(primary);
 }

 if(needsUpload&&!summary.file_replacement_allowed)main.append(el('p','The original file can’t be replaced after knowledge building has started. Add another material to use a different file.','muted'));

 if(summary.has_usable_knowledge){
  const use=actions(
   button('Explore ideas',()=>openScopedKnowledge()),
   button('Use in Create',()=>openCreate({request:sameSourceContext&&exploreState?.query||interactionDraft.originalRequest||'',materials:[id],library:source.library_id||null,selectedIds:selectedForSource}))
  );use.className='actions material-use-actions';main.append(use);
  if(summary.readiness==='partly_ready'&&summary.next_action==='continue_building')main.append(button('Continue building',build,'material-secondary-build'));
  let result;
  try{result=await api(`/sources/${id}/knowledge-units`);}catch{result={items:[],unavailable:true};}
  if(!active())return;
  const preview=el('section',undefined,'material-knowledge');preview.append(el('h2','Knowledge from this material'));
  if(result.unavailable)preview.append(el('p','Available knowledge could not be loaded right now. You can still ask, explore, or use this material in Create.','muted'));
  else if(!result.items?.length)preview.append(el('p','Usable knowledge is recorded for this material, but no ideas are available to preview right now. You can still ask a source-grounded question.','muted'));
  else for(const group of result.items.slice(0,5)){
   const asset=group.canonical_asset||{},idea=el('article',undefined,'material-idea');
   idea.append(el('h3',asset.title||'Knowledge idea'));
   if(asset.what_it_says)idea.append(el('p',asset.what_it_says,'material-idea-summary'));
   const evidence=detail('Source & evidence');evidence.className='material-evidence';
   const trail=group.evidence_trail?.length?group.evidence_trail:[{evidence:asset.evidence,chapter_or_section:asset.chapter_or_section}].filter(item=>item.evidence);
   for(const item of trail){
    const sourceLabel=source.title+(item.chapter_or_section?` · ${item.chapter_or_section}`:'');
    evidence.append(el('p',sourceLabel,'muted'),el('blockquote',item.evidence,'evidence'));
   }
   if(!trail.length)evidence.append(el('p','Evidence is not available in this preview.','muted'));
   idea.append(evidence);preview.append(idea);
  }
  main.append(preview);
 }

 if(summary.recovery?.some(item=>item.allowed)){
  const eligible=summary.recovery.filter(item=>item.allowed);
  const recovery=card('Resolve a build issue',summary.has_usable_knowledge?'Existing knowledge remains available while you resolve this issue.':'The previous build stopped before completion. Resolving it does not build knowledge; continue explicitly afterward.');
  recovery.append(button(eligible.length>1?'Resolve build issues':'Resolve build issue',async()=>{
   for(const item of eligible)await api(`/knowledge-extractions/${encodeURIComponent(item.job_id)}/recover`,{method:'POST'});
   if(active())await navigate('material',{id,replace:true});
  }));main.append(recovery);
 }

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
 }else if(source.file_path&&!summary.file_replacement_allowed)manage.append(el('p','The original file can’t be replaced after knowledge building has started. Add another material to use a different file.','muted'));
 manage.append(button('Delete material',async()=>{
  if(!confirm('Delete this material, its original file, its knowledge, and saved work histories that use its knowledge? This cannot be undone.'))return;
  await api(`/sources/${encodeURIComponent(id)}?delete_outputs=true`,{method:'DELETE'});
  if(!active())return;state.selected.clear();state.source=null;
  if(await navigate('library',{replace:true}))message('Material and related saved work were deleted.');
 },'danger'));
 main.append(manage);

 const advanced=detail('Advanced / Developer');advanced.className='material-advanced';main.append(advanced);
 let diagnosticsLoaded=false,diagnosticsLoading=false;
 advanced.ontoggle=()=>{
  if(!advanced.open||diagnosticsLoaded||diagnosticsLoading)return;
  diagnosticsLoading=true;
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
      const chunkId=fd.get('Chunk');
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
    advanced.append(diagnostics);diagnosticsLoaded=true;
   }catch(error){if(active())message('Advanced diagnostics could not be loaded. Material knowledge and actions remain available.',true);}
   finally{diagnosticsLoading=false;}
  });
 };
}
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
