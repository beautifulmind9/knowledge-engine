// Browser-owned, in-tab capture only. File selection never writes to the server.
export const MATERIAL_EXTENSIONS = ['.pdf','.epub','.docx','.txt','.md','.html','.htm','.csv','.json'];
export const MAX_MATERIAL_BYTES = 50_000_000;

export function validateMaterial(file) {
  if (!file || file.size === 0) throw Error('The uploaded file is empty.');
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (!MATERIAL_EXTENSIONS.includes(extension)) throw Error('Unsupported file type. Choose PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON.');
  if (file.size > MAX_MATERIAL_BYTES) throw Error('The uploaded file exceeds the 50 MB (50,000,000 bytes) per-file limit.');
  return extension;
}

export function suggestedMaterialTitle(filename) {
  const title = filename.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return (title ? title[0].toLocaleUpperCase() + title.slice(1) : 'Untitled material').slice(0,500);
}

export function newMaterialAdd(libraries, currentLibrary) {
  return {file:null,title:'',titleSuggested:'',titleUserConfirmed:false,author:'',authorUserConfirmed:false,libraryId:libraries.find(l=>l.id===currentLibrary)?.id || libraries[0]?.id || null,
    libraryName:'My Library',sourceId:null,uploaded:false,read:false,busy:false,error:null,readFailure:null,replacementSelected:false};
}

export function newMaterialAddBatch(libraries, currentLibrary) {
  const destination = newMaterialAdd(libraries, currentLibrary);
  return {libraryId:destination.libraryId,libraryName:destination.libraryName,items:[],invalidFiles:[],busy:false};
}

export function selectMaterialFiles(batch, files) {
  batch.items=[];batch.invalidFiles=[];
  for (const file of Array.from(files||[])) {
    try {
      validateMaterial(file);
      const titleSuggested=suggestedMaterialTitle(file.name);
      batch.items.push({...newMaterialAdd([],null),file,title:titleSuggested,titleSuggested,libraryId:batch.libraryId,libraryName:batch.libraryName});
    } catch(error) {
      batch.invalidFiles.push({name:file?.name||'Selected file',message:error.message});
    }
  }
  return batch;
}

function addFailureMessage(stage,error) {
  if(stage==='destination')return 'The destination could not be created. No material was added; check the destination and try again.';
  if(stage==='source')return 'The material record could not be created. Nothing was uploaded; check the title and try again.';
  if(stage==='upload'){
    if(error.status===413||/50 MB|too large/i.test(error.message))return 'This file is larger than 50 MB. Choose a smaller file.';
    if(/unsupported file type/i.test(error.message))return 'This file type is not supported. Choose PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON.';
    if(/uploaded file is empty|file is empty/i.test(error.message))return 'This file is empty. Choose another file.';
    return 'The file could not be uploaded right now. Your material record is saved; try uploading again.';
  }
  if(stage==='read')return 'The file was uploaded, but reading could not finish. Your material and file are saved; retry reading or choose another supported file.';
  return 'Material addition could not be completed. Your saved material is still available; check its status before trying again.';
}

// Each acknowledged durable identity is retained before the next operation.
// No provider endpoint is used; a failed step requires another explicit action.
export async function addMaterial(draft, api, makeUpload, progress=()=>{}) {
  if(draft.uploaded && draft.readFailure==='ocr_required') throw Error('Choose a different file with selectable text. OCR is not supported.');
  validateMaterial(draft.file);
  if (!draft.title.trim()) throw Error('Enter a title for this material.');
  if (!draft.libraryId && !draft.libraryName.trim()) throw Error('Enter a destination name.');
  if (draft.busy) return false;
  const timingNow=()=>{try{return globalThis.performance?.now?.()??Date.now();}catch{return Date.now();}};
  const timing=(event,start,extra={})=>{try{console.info('KE_PERF',{event,duration_ms:Math.round((timingNow()-start)*100)/100,...extra});}catch{}};
  const flowStarted=timingNow();let savedAt=draft.__keTimingSavedAt??(draft.uploaded?flowStarted:null);
  draft.busy=true;draft.error=null;
  let stage='destination';
  try {
    if (!draft.libraryId) {
      progress('Creating destination…');
      const library=await api('/libraries',{method:'POST',body:{name:draft.libraryName.trim(),description:''}});
      draft.libraryId=library.id;
    }
    stage='source';
    if (!draft.sourceId) {
      progress('Adding material…');
      const author=draft.author.trim();
      const source=await api('/sources',{method:'POST',body:{library_id:draft.libraryId,title:draft.title.trim(),author:author||null,source_type:'document',title_origin:draft.titleUserConfirmed?'user_confirmed':'filename',author_origin:draft.authorUserConfirmed?'user_confirmed':'unconfirmed'}});
      draft.sourceId=source.id;
    }
    stage='upload';
    if (!draft.uploaded) {
      progress('Uploading material…');
      await api(`/sources/${draft.sourceId}/upload`,{method:'POST',body:makeUpload(draft.file)});
      draft.uploaded=true;draft.replacementSelected=false;
      draft.__keTimingSavedAt=timingNow();
      draft.__keTimingUploadedAt=draft.__keTimingSavedAt;
      savedAt=draft.__keTimingSavedAt;
      timing('material_safely_saved',flowStarted,{source_id:draft.sourceId,file_size_bytes:draft.file?.size,result:'success'});
    }
    stage='read';
    if (!draft.read) {
      progress('Reading source…');
      await api(`/sources/${draft.sourceId}/process`,{method:'POST'});
      draft.read=true;draft.readFailure=null;
      draft.__keTimingReadAt=timingNow();
      timing('material_read_complete',savedAt??flowStarted,{source_id:draft.sourceId,result:'success'});
    }
    return true;
  } catch(error) {
    timing('material_add_stage',flowStarted,{source_id:draft.sourceId||undefined,stage,result:'error'});
    if(stage==='read'){
      // Trust the structured server classification, never parser-message matching.
      const summary=await api(`/sources/${draft.sourceId}/summary`).catch(()=>null);
      draft.readFailure=summary?.attention_category||null;
    }
    draft.error={stage,message:addFailureMessage(stage,error)};
    throw Error(draft.error.message);
  } finally { draft.busy=false; }
}

// Process the selected files independently. A failed file keeps its own
// durable identity and does not prevent its siblings from being added.
export async function addMaterials(batch, api, makeUpload, progress=()=>{}) {
  if(batch.busy)return {added:0,failed:0,results:[]};
  batch.busy=true;
  const perfNow=()=>{try{return globalThis.performance?.now?.()??Date.now();}catch{return Date.now();}};
  const batchStarted=perfNow();
  const selected=batch.items.filter(item=>!item.read).length;
  try{console.info('KE_PERF',{event:'material_batch_start',selected_count:selected});}catch{}
  const results=[];
  let destinationUnavailable=false;
  let queuePosition=0;
  try {
    for(const draft of batch.items.filter(item=>!item.read)){
      queuePosition++;
      const queuedAt=perfNow();
      try{console.info('KE_PERF',{event:'material_batch_item',source_id:draft.sourceId||undefined,queue_position:queuePosition,selected_count:selected});}catch{}
      draft.libraryId=batch.libraryId;draft.libraryName=batch.libraryName;
      if(destinationUnavailable){
        draft.error={stage:'destination',message:'The destination could not be created. This material was not added.'};
        results.push({draft,ok:false,error:new Error(draft.error.message)});continue;
      }
      try{
        await addMaterial(draft,api,makeUpload,progress);
        batch.libraryId=draft.libraryId;
        results.push({draft,ok:true});
      }catch(error){
        if(draft.libraryId)batch.libraryId=draft.libraryId;
        else if(draft.error?.stage==='destination')destinationUnavailable=true;
        results.push({draft,ok:false,error});
      }
      try{console.info('KE_PERF',{event:'material_batch_item_complete',source_id:draft.sourceId||undefined,queue_position:queuePosition,item_elapsed_ms:Math.round((perfNow()-queuedAt)*100)/100,result:draft.read?'read':'error'});}catch{}
    }
    return {added:results.filter(result=>result.ok).length,failed:results.filter(result=>!result.ok).length,results};
  }finally{batch.busy=false;try{console.info('KE_PERF',{event:'material_batch_complete',selected_count:selected,saved_count:results.filter(x=>x.draft.uploaded).length,read_count:results.filter(x=>x.ok).length,duration_ms:Math.round((perfNow()-batchStarted)*100)/100});}catch{}}
}
