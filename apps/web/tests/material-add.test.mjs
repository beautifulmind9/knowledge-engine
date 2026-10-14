import {test} from 'node:test';
import assert from 'node:assert/strict';
import {MATERIAL_EXTENSIONS,MAX_MATERIAL_BYTES,validateMaterial,suggestedMaterialTitle,newMaterialAdd,newMaterialAddBatch,selectMaterialFiles,addMaterial,addMaterials} from '../material-add.js';

const file={name:'my_workshop_notes.pdf',size:1024};
function fixture(libraries=[],current=null){
 const draft=newMaterialAdd(libraries,current);draft.file=file;draft.title=suggestedMaterialTitle(file.name);
 const calls=[];let failure=null;
 const api=async(path,options)=>{calls.push({path,options});if(path===failure)throw Error('Synthetic failure');return {id:path==='/libraries'?'new-library':'new-source'};};
 return {draft,calls,fail:path=>{failure=path;},run:()=>addMaterial(draft,api,f=>({file:f}))};
}
test('filename title is a conservative Unicode-preserving editable suggestion',()=>{
 for(const [input,expected] of [['my_workshop_notes.pdf','My workshop notes'],['The_Workshop-Survival_Guide.docx','The Workshop Survival Guide'],['café_学习.PDF','Café 学习'],['NASA_notes.txt','NASA notes']])assert.equal(suggestedMaterialTitle(input),expected);
});
test('local validation matches backend extensions and byte boundary before any writes',async()=>{
 assert.equal(MAX_MATERIAL_BYTES,50_000_000);
 assert.equal(MATERIAL_EXTENSIONS.length,9);
 for(const invalid of [{...file,size:0},{...file,size:MAX_MATERIAL_BYTES+1},{...file,name:'image.png'}]){
  const f=fixture();f.draft.file=invalid;await assert.rejects(f.run);assert.equal(f.calls.length,0);
 }
 assert.equal(validateMaterial({...file,size:MAX_MATERIAL_BYTES}),'.pdf');
 assert.throws(()=>validateMaterial({...file,size:MAX_MATERIAL_BYTES+1}),/50 MB \(50,000,000 bytes\) per-file limit/);
 assert.equal(validateMaterial({...file,name:'NOTES.TXT'}),'.txt');
});
test('an oversized selected file does not invalidate valid batch siblings',()=>{
 const batch=newMaterialAddBatch([],null);
 selectMaterialFiles(batch,[{name:'at-limit.pdf',size:MAX_MATERIAL_BYTES},{name:'too-large.pdf',size:MAX_MATERIAL_BYTES+1},{name:'sibling.txt',size:100}]);
 assert.deepEqual(batch.items.map(item=>item.file.name),['at-limit.pdf','sibling.txt']);
 assert.deepEqual(batch.invalidFiles.map(item=>item.name),['too-large.pdf']);
});
test('empty account proposes destination without writes then creates library/source/upload/read only',async()=>{
 const f=fixture();assert.equal(f.draft.libraryName,'My Library');assert.equal(f.draft.libraryId,null);assert.equal(f.calls.length,0);
 await f.run();assert.deepEqual(f.calls.map(c=>c.path),['/libraries','/sources','/sources/new-source/upload','/sources/new-source/process']);
 assert.equal(f.calls[0].options.body.name,'My Library');assert.equal(f.calls[1].options.body.author,null);assert.equal(f.draft.read,true);
});
test('existing destination defaults to current or first visible choice and can change before Add',async()=>{
 const libs=[{id:'first',name:'First'},{id:'current',name:'Current'}];
 const f=fixture(libs,'current');assert.equal(f.draft.libraryId,'current');
 assert.equal(newMaterialAdd(libs,null).libraryId,'first');
 f.draft.libraryId='first';f.draft.title='Corrected title';f.draft.author='An author';f.draft.titleUserConfirmed=true;f.draft.authorUserConfirmed=true;await f.run();
 assert.equal(f.calls[0].path,'/sources');assert.deepEqual(f.calls[0].options.body,{library_id:'first',title:'Corrected title',author:'An author',source_type:'document',title_origin:'user_confirmed',author_origin:'user_confirmed'});
});
test('untouched filename title and blank author are explicitly provisional',async()=>{
 const f=fixture();await f.run();const created=f.calls.find(call=>call.path==='/sources').options.body;
 assert.equal(created.title_origin,'filename');assert.equal(created.author_origin,'unconfirmed');
});
test('explicitly cleared optional author is confirmed blank and cannot be filled by later reading',async()=>{
 const f=fixture();f.draft.author='';f.draft.authorUserConfirmed=true;await f.run();const created=f.calls.find(call=>call.path==='/sources').options.body;
 assert.equal(created.author,null);assert.equal(created.author_origin,'user_confirmed');
});
test('known destination survives source creation failure and retry does not duplicate it',async()=>{
 const f=fixture();f.fail('/sources');await assert.rejects(f.run,/material record could not be created/i);
 assert.equal(f.draft.libraryId,'new-library');assert.equal(f.draft.sourceId,null);
 f.fail(null);await f.run();assert.equal(f.calls.filter(c=>c.path==='/libraries').length,1);
});
test('upload failure retains source identity and gives a safe actionable message',async()=>{
 const f=fixture();f.fail('/sources/new-source/upload');await assert.rejects(f.run,/file could not be uploaded right now.*material record is saved/i);
 assert.equal(f.draft.sourceId,'new-source');assert.equal(f.draft.uploaded,false);
 f.fail(null);await f.run();assert.equal(f.calls.filter(c=>c.path==='/sources').length,1);
 assert.equal(f.calls.filter(c=>c.path.endsWith('/upload')).length,2);
});
test('read failure retains source and upload; retry only reads with safe actionable copy',async()=>{
 const f=fixture();f.fail('/sources/new-source/process');await assert.rejects(f.run,/uploaded, but reading could not finish.*retry reading/i);
 assert.equal(f.draft.uploaded,true);assert.equal(f.draft.read,false);
 f.fail(null);await f.run();assert.equal(f.calls.filter(c=>c.path==='/sources').length,1);assert.equal(f.calls.filter(c=>c.path.endsWith('/upload')).length,1);
 assert.equal(f.calls.filter(c=>c.path.endsWith('/process')).length,2);assert.ok(!f.calls.some(c=>/interpret|generate/.test(c.path)));
});

test('upload failure categories distinguish size, type, empty, storage and generic add failures',async()=>{
 const cases=[
  [413,'Upload limit','larger than 50 MB'],
  [400,'Unsupported file type.','file type is not supported'],
  [400,'The uploaded file is empty.','file is empty'],
  [503,'safe storage message','could not be uploaded right now'],
  [400,'private or unfamiliar server detail','could not be uploaded right now'],
 ];
 for(const [status,detail,expected] of cases){
  const draft=fixture().draft;let failed=false;
  const api=async path=>{
   if(path==='/libraries')return {id:'lib'};
   if(path==='/sources')return {id:'source'};
   if(path.endsWith('/upload')&&!failed){failed=true;const error=Error(detail);error.status=status;throw error;}
   return {};
  };
  await assert.rejects(addMaterial(draft,api,file=>({file})),new RegExp(expected,'i'));
  assert.equal(draft.error.stage,'upload');
  assert.ok(!draft.error.message.includes('private or unfamiliar server detail'));
 }
 const draft=fixture().draft;
 const api=async path=>{if(path==='/libraries')throw Error('private create detail');throw Error(path);};
 await assert.rejects(addMaterial(draft,api,file=>({file})),/destination could not be created.*check the destination/i);
 assert.ok(!draft.error.message.includes('private create detail'));
});
test('destination failure leaves no source, and in-flight duplicate activation cannot dispatch twice',async()=>{
 const f=fixture();f.fail('/libraries');await assert.rejects(f.run,/destination could not be created/i);assert.equal(f.calls.length,1);
 let release;const pending=new Promise(resolve=>{release=resolve;});let calls=0;
 const draft=fixture().draft;
 const api=async path=>{calls++;if(path==='/libraries')await pending;return {id:'id'};};
 const first=addMaterial(draft,api,f=>f);assert.equal(await addMaterial(draft,api,f=>f),false);release();await first;assert.equal(calls,4);
});

test('structured OCR classification blocks unchanged reread; replacement reuses source',async()=>{
 const f=fixture();let failRead=true;const calls=[];
 const api=async(path,options)=>{calls.push({path,options});if(path.endsWith('/summary'))return {attention_category:'ocr_required'};if(path.endsWith('/process')&&failRead)throw Error('Safe OCR message');return {id:path==='/libraries'?'lib':'source'};};
 const run=()=>addMaterial(f.draft,api,file=>({file}));
 await assert.rejects(run,/file was uploaded, but reading could not finish/i);assert.equal(f.draft.readFailure,'ocr_required');
 const before=calls.length;await assert.rejects(run,/Choose a different file/);assert.equal(calls.length,before);
 f.draft.file={name:'readable.txt',size:50};f.draft.uploaded=false;f.draft.replacementSelected=true;failRead=false;
 await run();assert.equal(calls.filter(c=>c.path==='/sources').length,1);assert.equal(f.draft.sourceId,'source');assert.equal(f.draft.read,true);
 assert.ok(!calls.some(c=>/generate|interpret/.test(c.path)));
});

test('multi-file selection validates locally and suggests each title without writes',()=>{
 const batch=newMaterialAddBatch([{id:'library-1',name:'Reading'}],'library-1');
 selectMaterialFiles(batch,[{name:'Everyday_Design.pdf',size:400},{name:'bad.exe',size:400},{name:'empty.txt',size:0},{name:'Practice.md',size:100}]);
 assert.deepEqual(batch.items.map(item=>item.title),['Everyday Design','Practice']);
 assert.equal(batch.items.every(item=>item.libraryId==='library-1'),true);
 assert.deepEqual(batch.invalidFiles.map(item=>item.name),['bad.exe','empty.txt']);
});

test('multi-file Add keeps successful siblings and retries a failed upload using its source identity',async()=>{
 const batch=newMaterialAddBatch([],null);
 selectMaterialFiles(batch,[{name:'one.pdf',size:100},{name:'two.txt',size:100},{name:'three.md',size:100}]);
 const calls=[],sources=[];let failOnce=true,nextSource=0;
 const api=async(path,options={})=>{
  calls.push({path,options});
  if(path==='/libraries')return {id:'created-library'};
  if(path==='/sources'){const source={id:`source-${++nextSource}`};sources.push(source);return source;}
  if(path.endsWith('/upload')&&path.startsWith('/sources/source-2')&&failOnce){failOnce=false;throw Error('Synthetic upload failure');}
  if(path.endsWith('/upload'))return {};
  if(path.endsWith('/process'))return {processed_this_run:1};
  throw Error(path);
 };
 const makeUpload=file=>({file});
 const first=await addMaterials(batch,api,makeUpload);
 assert.deepEqual([first.added,first.failed],[2,1]);
 assert.deepEqual(batch.items.map(item=>item.read),[true,false,true]);
 const failedIdentity=batch.items[1].sourceId;assert.equal(failedIdentity,'source-2');
 assert.equal(calls.filter(call=>call.path==='/libraries').length,1);
 assert.equal(calls.filter(call=>call.path==='/sources').length,3);
 const second=await addMaterials(batch,api,makeUpload);
 assert.deepEqual([second.added,second.failed],[1,0]);
 assert.equal(batch.items.every(item=>item.read),true);
 assert.equal(batch.items[1].sourceId,failedIdentity);
 assert.equal(calls.filter(call=>call.path==='/sources').length,3);
 assert.equal(calls.filter(call=>call.path.endsWith('/upload')).length,4);
 assert.equal(calls.filter(call=>call.path.endsWith('/process')).length,3);
 assert.equal(calls.some(call=>/interpret|generate/.test(call.path)),false);
});
