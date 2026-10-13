// Browser-owned, in-tab capture only. File selection never writes to the server.
export const MATERIAL_EXTENSIONS = ['.pdf','.epub','.docx','.txt','.md','.html','.htm','.csv','.json'];
export const MAX_MATERIAL_BYTES = 25 * 1024 * 1024;

export function validateMaterial(file) {
  if (!file || file.size === 0) throw Error('The uploaded file is empty.');
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (!MATERIAL_EXTENSIONS.includes(extension)) throw Error('Unsupported file type. Choose PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON.');
  if (file.size > MAX_MATERIAL_BYTES) throw Error('The uploaded file exceeds the 25 MiB limit.');
  return extension;
}

export function suggestedMaterialTitle(filename) {
  const title = filename.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
  return (title ? title[0].toLocaleUpperCase() + title.slice(1) : 'Untitled material').slice(0,500);
}

export function newMaterialAdd(libraries, currentLibrary) {
  return {file:null,title:'',author:'',libraryId:libraries.find(l=>l.id===currentLibrary)?.id || libraries[0]?.id || null,
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
      batch.items.push({...newMaterialAdd([],null),file,title:suggestedMaterialTitle(file.name),libraryId:batch.libraryId,libraryName:batch.libraryName});
    } catch(error) {
      batch.invalidFiles.push({name:file?.name||'Selected file',message:error.message});
    }
  }
  return batch;
}

// Each acknowledged durable identity is retained before the next operation.
// No provider endpoint is used; a failed step requires another explicit action.
export async function addMaterial(draft, api, makeUpload, progress=()=>{}) {
  if(draft.uploaded && draft.readFailure==='ocr_required') throw Error('Choose a different file with selectable text. OCR is not supported.');
  validateMaterial(draft.file);
  if (!draft.title.trim()) throw Error('Enter a title for this material.');
  if (!draft.libraryId && !draft.libraryName.trim()) throw Error('Enter a destination name.');
  if (draft.busy) return false;
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
      const source=await api('/sources',{method:'POST',body:{library_id:draft.libraryId,title:draft.title.trim(),author:draft.author.trim()||null,source_type:'document'}});
      draft.sourceId=source.id;
    }
    stage='upload';
    if (!draft.uploaded) {
      progress('Uploading material…');
      await api(`/sources/${draft.sourceId}/upload`,{method:'POST',body:makeUpload(draft.file)});
      draft.uploaded=true;draft.replacementSelected=false;
    }
    stage='read';
    if (!draft.read) {
      progress('Reading source…');
      await api(`/sources/${draft.sourceId}/process`,{method:'POST'});
      draft.read=true;draft.readFailure=null;
    }
    return true;
  } catch(error) {
    if(stage==='read'){
      // Trust the structured server classification, never parser-message matching.
      const summary=await api(`/sources/${draft.sourceId}/summary`).catch(()=>null);
      draft.readFailure=summary?.attention_category||null;
    }
    const prefix={destination:'The destination could not be created. Material has not been added.',source:'The destination is kept. Material has not been added yet.',upload:'Material record kept. The file upload did not complete.',read:'Material and file kept. Reading did not complete.'}[stage];
    draft.error={stage,message:`${prefix} ${error.message}`};
    throw Error(draft.error.message);
  } finally { draft.busy=false; }
}

// Process the selected files independently. A failed file keeps its own
// durable identity and does not prevent its siblings from being added.
export async function addMaterials(batch, api, makeUpload, progress=()=>{}) {
  if(batch.busy)return {added:0,failed:0,results:[]};
  batch.busy=true;
  const results=[];
  let destinationUnavailable=false;
  try {
    for(const draft of batch.items.filter(item=>!item.read)){
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
    }
    return {added:results.filter(result=>result.ok).length,failed:results.filter(result=>!result.ok).length,results};
  }finally{batch.busy=false;}
}
