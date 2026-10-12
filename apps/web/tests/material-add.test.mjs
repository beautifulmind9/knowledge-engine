import {test} from 'node:test';
import assert from 'node:assert/strict';
import {MATERIAL_EXTENSIONS,MAX_MATERIAL_BYTES,validateMaterial,suggestedMaterialTitle,newMaterialAdd,addMaterial} from '../material-add.js';

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
 assert.equal(MATERIAL_EXTENSIONS.length,9);
 for(const invalid of [{...file,size:0},{...file,size:MAX_MATERIAL_BYTES+1},{...file,name:'image.png'}]){
  const f=fixture();f.draft.file=invalid;await assert.rejects(f.run);assert.equal(f.calls.length,0);
 }
 assert.equal(validateMaterial({...file,size:MAX_MATERIAL_BYTES}),'.pdf');
 assert.equal(validateMaterial({...file,name:'NOTES.TXT'}),'.txt');
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
 f.draft.libraryId='first';f.draft.title='Corrected title';f.draft.author='An author';await f.run();
 assert.equal(f.calls[0].path,'/sources');assert.deepEqual(f.calls[0].options.body,{library_id:'first',title:'Corrected title',author:'An author',source_type:'document'});
});
test('known destination survives source creation failure and retry does not duplicate it',async()=>{
 const f=fixture();f.fail('/sources');await assert.rejects(f.run,/Material has not been added yet/);
 assert.equal(f.draft.libraryId,'new-library');assert.equal(f.draft.sourceId,null);
 f.fail(null);await f.run();assert.equal(f.calls.filter(c=>c.path==='/libraries').length,1);
});
test('upload failure retains source identity and explicit retry reuses it',async()=>{
 const f=fixture();f.fail('/sources/new-source/upload');await assert.rejects(f.run,/Material record kept/);
 assert.equal(f.draft.sourceId,'new-source');assert.equal(f.draft.uploaded,false);
 f.fail(null);await f.run();assert.equal(f.calls.filter(c=>c.path==='/sources').length,1);
 assert.equal(f.calls.filter(c=>c.path.endsWith('/upload')).length,2);
});
test('read failure retains source and upload; retry only reads, never builds',async()=>{
 const f=fixture();f.fail('/sources/new-source/process');await assert.rejects(f.run,/Material and file kept/);
 assert.equal(f.draft.uploaded,true);assert.equal(f.draft.read,false);
 f.fail(null);await f.run();assert.equal(f.calls.filter(c=>c.path==='/sources').length,1);assert.equal(f.calls.filter(c=>c.path.endsWith('/upload')).length,1);
 assert.equal(f.calls.filter(c=>c.path.endsWith('/process')).length,2);assert.ok(!f.calls.some(c=>/interpret|generate/.test(c.path)));
});
test('destination failure leaves no source, and in-flight duplicate activation cannot dispatch twice',async()=>{
 const f=fixture();f.fail('/libraries');await assert.rejects(f.run,/Material has not been added/);assert.equal(f.calls.length,1);
 let release;const pending=new Promise(resolve=>{release=resolve;});let calls=0;
 const draft=fixture().draft;
 const api=async path=>{calls++;if(path==='/libraries')await pending;return {id:'id'};};
 const first=addMaterial(draft,api,f=>f);assert.equal(await addMaterial(draft,api,f=>f),false);release();await first;assert.equal(calls,4);
});

test('structured OCR classification blocks unchanged reread; replacement reuses source',async()=>{
 const f=fixture();let failRead=true;const calls=[];
 const api=async(path,options)=>{calls.push({path,options});if(path.endsWith('/summary'))return {attention_category:'ocr_required'};if(path.endsWith('/process')&&failRead)throw Error('Safe OCR message');return {id:path==='/libraries'?'lib':'source'};};
 const run=()=>addMaterial(f.draft,api,file=>({file}));
 await assert.rejects(run,/Material and file kept/);assert.equal(f.draft.readFailure,'ocr_required');
 const before=calls.length;await assert.rejects(run,/Choose a different file/);assert.equal(calls.length,before);
 f.draft.file={name:'readable.txt',size:50};f.draft.uploaded=false;f.draft.replacementSelected=true;failRead=false;
 await run();assert.equal(calls.filter(c=>c.path==='/sources').length,1);assert.equal(f.draft.sourceId,'source');assert.equal(f.draft.read,true);
 assert.ok(!calls.some(c=>/generate|interpret/.test(c.path)));
});
