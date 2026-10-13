// Synthetic APIs only: material-first acceptance never contacts a provider.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||'/tmp/ke-material-add-review';
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),errors=[];
 async function fixture({empty=false,mobile=false,scoped=false,uploadFailure=false,batchUploadFailure=false,readFailure=false,sourceFailure=false,genericReadFailure=false}={}){
  const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:mobile,hasTouch:mobile});
  page.on('pageerror',e=>errors.push(e.message));
  const libraries=empty?[]:[{id:'l1',name:'Reading'},{id:'l2',name:'Workshop resources'}],sources=[],calls=[];
  let uploadFails=uploadFailure,batchUploadFails=batchUploadFailure,readFails=readFailure,sourceFails=sourceFailure;
  await page.route('http://ke.test/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method();
   if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
   calls.push({path:p,method,body:method==='POST'&&!p.endsWith('/upload')?request.postDataJSON():null});let data;
   if(p==='/libraries'&&method==='GET')data={items:libraries};
   else if(p==='/libraries'){data={id:'new-library',...request.postDataJSON()};libraries.push(data);}
   else if(p==='/sources'&&method==='GET')data={items:sources};
   else if(p==='/sources/summaries')data=sources.map(source=>{const ready=!!source.chunks_path;return {source_id:source.id,readiness:ready?'ready_to_build':'added',completed_parts:source.completed_parts||0,total_parts:ready?3:0,coverage_text:ready?`${source.completed_parts||0} of 3 parts ready`:null,has_usable_knowledge:!!source.usable,operation:'idle',attention_category:source.reading_failure||null,attention_message:null,file_state:source.file_path?'available':'unattached',read_state:ready?'read':source.reading_failure||'not_read',next_action:ready?'build_knowledge':'read_source',recovery:[]};});
   else if(p==='/sources'){
    if(sourceFails)return route.fulfill({status:400,json:{detail:'Source could not be created.'}});
    data={id:'s'+(sources.length+1),...request.postDataJSON(),processing_status:'created'};sources.push(data);
   }else if(p.endsWith('/upload')){
    data=sources.find(s=>p.includes('/'+s.id+'/'));
    if(uploadFails||batchUploadFails&&data?.id==='s2'){if(batchUploadFails)batchUploadFails=false;return route.fulfill({status:400,json:{detail:'Upload interrupted. Try again.'}});}
    data.file_path='synthetic-file';
   }else if(p.endsWith('/process')){
    data=sources.find(s=>p.includes('/'+s.id+'/'));
    if(readFails){data.reading_failure=genericReadFailure?'read_failed':'ocr_required';return route.fulfill({status:400,json:{detail:genericReadFailure?'This file could not be read. Try reading again or supply a readable file.':'This PDF has no extractable text. OCR is not supported; supply a PDF with selectable text or another supported file.'}});}
    data.chunks_path='synthetic-parts';data.reading_failure=null;
   }else if(p.endsWith('/summary')){
    const source=sources.find(s=>p.includes('/'+s.id+'/')),ready=!!source.chunks_path;
    data={source_id:source.id,readiness:ready?(source.completed_parts===3?'ready':source.completed_parts?'partly_ready':'ready_to_build'):'added',total_parts:ready?3:0,completed_parts:source.completed_parts||0,coverage_text:ready?`${source.completed_parts||0} of 3 parts ready`:null,has_usable_knowledge:!!source.usable,operation:'idle',attention_category:source.reading_failure||source.build_attention||null,attention_message:source.reading_failure?(genericReadFailure?'This file could not be read. Try reading again.':'This PDF has no extractable text. OCR is not supported.'):source.build_attention?'The previous knowledge-building attempt stopped before completion.':null,file_state:source.file_path?'available':'unattached',read_state:ready?'read':source.reading_failure||'not_read',next_action:ready?(source.completed_parts===3?'use_knowledge':source.completed_parts?'continue_building':'build_knowledge'):source.reading_failure==='ocr_required'?'supply_readable_file':'read_source',file_replacement_allowed:true,recovery:[]};
   }else if(p==='/usage')data={configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:10,paused:false,daily_limit_reached:false};
   else if(/^\/sources\/[^/]+$/.test(p))data=sources.find(s=>s.id===p.split('/').at(-1));
   else if(p.endsWith('/knowledge-units'))data={items:[{canonical_asset:{title:'Practice breaks',what_it_says:'Allow time for reflection after practice.'}}]};
   else if(p==='/outputs/modes')data={items:[{id:'writing',label:'Writing',formats:['Essay']}]};
   else if(p==='/outputs')data={items:[],count:0};
   else throw Error('Unexpected API '+method+' '+p);
   return route.fulfill({json:data});
  });
  await page.goto('http://ke.test/#/library?add=1'+(scoped?'&library=l2':''));await page.locator('#material-add input[type=file]').waitFor();
  return {page,calls,sources,libraries,posts:()=>calls.filter(c=>c.method==='POST'),uploadWorks:()=>{uploadFails=false;batchUploadFails=false;},readWorks:()=>readFails=false,sourceWorks:()=>sourceFails=false,
   file:async(name='my_workshop_notes.pdf',buffer=Buffer.from('Synthetic text'))=>page.locator('#material-add input[name=file]').setInputFiles({name,mimeType:'application/pdf',buffer}),
   add:()=>page.locator('#material-confirmation').getByRole('button',{name:'Add material',exact:true}).click(),
   shot:name=>(!process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER||name.match(process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER))?page.screenshot({path:path.join(out,name+'.png'),fullPage:true}):undefined};
 }
 try{
  let f=await fixture({empty:true});await f.shot('01-empty-before-file');
  assert.equal(await f.page.locator('[name=title]').count(),0);assert.equal(f.posts().length,0);
  await f.file();await f.page.getByText('Destination · My Library',{exact:true}).waitFor();await f.shot('02-file-confirmation');assert.equal(f.posts().length,0);
  await f.page.locator('#material-confirmation').getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(f.posts().length,0);assert.equal(await f.page.locator('[name=title]').count(),0);
  await f.file();await f.add();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();await f.shot('04-ready-to-build');
  assert.deepEqual(f.posts().map(c=>c.path),['/libraries','/sources','/sources/s1/upload','/sources/s1/process']);assert.equal(f.sources.length,1);
  assert.match(await f.page.locator('.material-status').textContent(),/Ready to build knowledge/);
  assert.equal(await f.page.getByRole('button',{name:'Browse useful ideas',exact:true}).count(),0);assert.equal(await f.page.getByRole('button',{name:'Create using this material',exact:true}).count(),0);assert.equal(await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).count(),1);
  await f.page.goBack();await f.page.locator('#material-add').waitFor();assert.equal(await f.page.locator('[name=title]').count(),0);await f.page.goForward();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();assert.equal(f.posts().length,4);await f.page.close();
  console.log('PASS empty account file-first/no selection writes/cancel/Add/read/explicit Build/history');

  f=await fixture({scoped:true});await f.file('The_Workshop-Survival_Guide.docx');await f.page.getByText('Destination · Workshop resources',{exact:true}).waitFor();
  assert.equal(await f.page.locator('[name=title]').inputValue(),'The Workshop Survival Guide');assert.equal(await f.page.locator('[name=author]').isVisible(),false);
  await f.shot('03-existing-confirmation');await f.page.getByText('Change destination',{exact:true}).click();await f.page.getByLabel('Destination',{exact:true}).selectOption('l1');
  await f.page.getByLabel('Title · suggested from filename').fill('My corrected title');await f.add();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();
  assert.equal(f.sources[0].library_id,'l1');assert.equal(f.sources[0].title,'My corrected title');assert.equal(f.sources[0].author,null);assert.equal(f.posts().length,3);await f.page.close();
  console.log('PASS current destination, editable title/destination, optional author');

  f=await fixture({empty:true});await f.page.locator('#material-add input[name=file]').setInputFiles([
   {name:'Everyday_Design.pdf',mimeType:'application/pdf',buffer:Buffer.from('Design material')},
   {name:'unsupported.png',mimeType:'image/png',buffer:Buffer.from('unsupported')},
   {name:'Practice_Notes.txt',mimeType:'text/plain',buffer:Buffer.from('Practice material')},
  ]);
  await f.page.getByText('2 materials · My Library',{exact:true}).waitFor();assert.equal(await f.page.locator('.material-batch-item').count(),2);assert.ok((await f.page.locator('#material-confirmation').textContent()).includes('unsupported.png: Unsupported file type'));
  await f.shot('08-multiple-material-confirmation');assert.equal(f.posts().length,0);
  await f.page.getByRole('button',{name:'Add 2 materials',exact:true}).click();await f.page.locator('.library-row').nth(1).waitFor();
  assert.equal(f.sources.length,2);assert.equal(f.posts().filter(call=>call.path==='/libraries').length,1);assert.equal(f.posts().filter(call=>call.path==='/sources').length,2);assert.equal(f.posts().filter(call=>call.path.endsWith('/upload')).length,2);assert.equal(f.posts().filter(call=>call.path.endsWith('/process')).length,2);assert.ok(f.posts().every(call=>! /interpret|generate/.test(call.path)));await f.page.close();
  console.log('PASS multiple material confirmation, mixed local validation and deterministic independent Add');

  f=await fixture({batchUploadFailure:true});await f.page.locator('#material-add input[name=file]').setInputFiles([
   {name:'One.pdf',mimeType:'application/pdf',buffer:Buffer.from('one')},{name:'Two.txt',mimeType:'text/plain',buffer:Buffer.from('two')},{name:'Three.md',mimeType:'text/markdown',buffer:Buffer.from('three')},
  ]);await f.page.getByRole('button',{name:'Add 3 materials',exact:true}).click();await f.page.getByRole('button',{name:'Retry 1 material',exact:true}).waitFor();
  assert.equal(f.sources.length,3);assert.equal(f.sources.filter(source=>!!source.chunks_path).length,2);await f.shot('09-multiple-upload-partial');
  assert.equal(await f.page.getByRole('button',{name:'Retry 1 material',exact:true}).count(),1);f.uploadWorks();await f.page.getByRole('button',{name:'Retry 1 material',exact:true}).click();await f.page.waitForFunction(()=>document.querySelectorAll('.library-rows .library-row').length===3);
  assert.equal(f.sources.filter(source=>!!source.chunks_path).length,3);assert.equal(f.posts().filter(call=>call.path==='/sources').length,3);await f.page.close();
  console.log('PASS partial batch Add keeps siblings and retries same failed source');

  f=await fixture({empty:true,sourceFailure:true});await f.file();await f.add();await f.page.getByRole('button',{name:'Retry Add material',exact:true}).waitFor();assert.equal(f.libraries.length,1);assert.equal(f.sources.length,0);
  f.sourceWorks();await f.page.getByRole('button',{name:'Retry Add material',exact:true}).click();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();assert.equal(f.posts().filter(c=>c.path==='/libraries').length,1);await f.page.close();

  f=await fixture({uploadFailure:true});await f.file();await f.add();await f.page.getByRole('button',{name:'Retry upload',exact:true}).waitFor();await f.shot('05-upload-resume');assert.equal(f.sources.length,1);
  f.uploadWorks();await f.page.getByRole('button',{name:'Retry upload',exact:true}).click();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();assert.equal(f.sources.length,1);assert.equal(f.posts().filter(c=>c.path==='/sources').length,1);await f.page.close();

  f=await fixture({readFailure:true});await f.file();await f.add();await f.page.getByRole('button',{name:'Choose a different file',exact:true}).waitFor();await f.shot('06-ocr-read-failure');assert.equal(f.sources.length,1);assert.ok(f.sources[0].file_path);
  assert.equal(await f.page.getByRole('button',{name:'Retry reading',exact:true}).count(),0);const before=f.posts().length;
  await f.page.locator('[name^="replacement_file-"]').setInputFiles({name:'readable.txt',mimeType:'text/plain',buffer:Buffer.from('Readable text')});assert.equal(f.posts().length,before);await f.page.getByRole('button',{name:'Use replacement file',exact:true}).waitFor();
  f.readWorks();await f.page.getByRole('button',{name:'Use replacement file',exact:true}).click();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();assert.equal(f.sources.length,1);assert.equal(f.posts().filter(c=>c.path.endsWith('/upload')).length,2);await f.page.close();
  f=await fixture({readFailure:true,genericReadFailure:true});await f.file();await f.add();await f.page.getByRole('button',{name:'Retry reading',exact:true}).waitFor();f.readWorks();await f.page.getByRole('button',{name:'Retry reading',exact:true}).click();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();assert.equal(f.posts().filter(c=>c.path.endsWith('/upload')).length,1);assert.equal(f.sources.length,1);await f.page.close();

  f=await fixture();await f.file();await f.add();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();f.sources[0].completed_parts=1;f.sources[0].usable=true;f.sources[0].build_attention='build_stopped';
  await f.page.reload();await f.page.getByRole('button',{name:'Build remaining 2 parts',exact:true}).waitFor();await f.page.getByRole('button',{name:'Ask this source',exact:true}).waitFor();await f.page.getByRole('button',{name:'Explore ideas',exact:true}).waitFor();await f.page.getByRole('button',{name:'Use in Create',exact:true}).waitFor();await f.shot('08-partly-ready-usable');
  f.sources[0].usable=false;await f.page.reload();await f.page.getByRole('button',{name:'Build remaining 2 parts',exact:true}).waitFor();assert.equal(await f.page.getByRole('button',{name:'Ask this source',exact:true}).count(),0);assert.equal(await f.page.getByRole('button',{name:'Explore ideas',exact:true}).count(),0);assert.equal(await f.page.getByRole('button',{name:'Use in Create',exact:true}).count(),0);
  f.sources[0].completed_parts=3;await f.page.reload();await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();await f.page.getByText('No usable knowledge is available from this material yet.',{exact:true}).waitFor();assert.equal(await f.page.getByRole('button',{name:'Ask this source',exact:true}).count(),0);assert.equal(await f.page.getByRole('button',{name:'Explore ideas',exact:true}).count(),0);assert.equal(await f.page.getByRole('button',{name:'Use in Create',exact:true}).count(),0);
  f.sources[0].usable=true;await f.page.reload();await f.page.getByRole('button',{name:'Ask this source',exact:true}).waitFor();await f.page.getByRole('button',{name:'Explore ideas',exact:true}).waitFor();await f.page.getByRole('button',{name:'Use in Create',exact:true}).waitFor();assert.ok(f.posts().every(c=>! /interpret|generate/.test(c.path)));await f.page.close();
  console.log('PASS source/upload/read failure and explicit same-identity resume, truthful OCR');

  f=await fixture();for(const [name,buffer] of [['empty.pdf',Buffer.alloc(0)],['unsupported.png',Buffer.from('x')]]){await f.file(name,buffer);await f.page.locator('#feedback.error').waitFor();assert.equal(f.posts().length,0);assert.equal(await f.page.locator('[name=title]').count(),0);}
  await f.page.locator('#material-add input[name=file]').setInputFiles({name:'large.txt',mimeType:'text/plain',buffer:Buffer.alloc(25*1024*1024+1)});await f.page.locator('#feedback.error').waitFor();assert.equal(f.posts().length,0);await f.page.close();

  f=await fixture({mobile:true,empty:true});await f.page.locator('#material-add input[name=file]').setInputFiles([
   {name:'café_workshop_notes.pdf',mimeType:'application/pdf',buffer:Buffer.from('one')},{name:'Planning_notes.txt',mimeType:'text/plain',buffer:Buffer.from('two')},
  ]);await f.shot('07-mobile-confirmation');
  assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));const fileBox=await f.page.locator('[name=file]').boundingBox(),titleBox=await f.page.locator('[name=title-0]').boundingBox();assert.ok(fileBox.y<titleBox.y);
  await f.page.locator('#material-confirmation').getByRole('button',{name:'Add 2 materials',exact:true}).scrollIntoViewIfNeeded();await f.page.getByRole('button',{name:'Add 2 materials',exact:true}).click();await f.page.waitForFunction(()=>document.querySelectorAll('.library-rows .library-row').length===2);assert.equal(f.posts().filter(c=>c.path==='/sources').length,2);await f.page.close();
  console.log('PASS browser validation and mobile ordering/overflow/reachable Add');

  f=await fixture();await f.page.getByRole('button',{name:'Create',exact:true}).click();await f.page.locator('[name=original_request]').fill('Write an essay in my voice');
  await f.page.getByRole('link',{name:'Knowledge Engine Home',exact:true}).click();await f.page.getByRole('button',{name:'Add to my library',exact:true}).click();await f.page.locator('[name=file]').waitFor();await f.file();await f.add();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();
  await f.page.getByRole('button',{name:'Create',exact:true}).click();await f.page.locator('[name=original_request]').waitFor();assert.equal(await f.page.locator('[name=original_request]').inputValue(),'Write an essay in my voice');assert.ok(f.posts().every(c=>! /interpret|generate/.test(c.path)));await f.page.close();
  console.log('PASS existing Create draft survives successful Add; zero provider endpoints');
  f=await fixture();let release,started;
  const held=new Promise(resolve=>release=resolve),reading=new Promise(resolve=>started=resolve);
  await f.page.route('**/sources/s1/process',async route=>{started();await held;f.sources[0].chunks_path='synthetic-parts';await route.fulfill({json:{}});});
  await f.file();await f.add();await reading;await f.page.getByRole('link',{name:'Knowledge Engine Home',exact:true}).click();await f.page.getByLabel('Your request',{exact:true}).waitFor();
  await f.page.goBack();await f.page.locator('#material-confirmation').waitFor();release();await f.page.locator('#material-confirmation').getByRole('button',{name:'Open material',exact:true}).waitFor();
  assert.ok(!f.page.url().includes('/material/'));assert.equal(f.sources.length,1);assert.equal(f.posts().filter(c=>c.path==='/sources').length,1);
  await f.page.locator('#material-confirmation').getByRole('button',{name:'Open material',exact:true}).click();await f.page.getByRole('button',{name:'Build remaining 3 parts',exact:true}).waitFor();await f.page.close();
  console.log('PASS navigation during pending read: no late redirect, same-identity continuation');

  assert.deepEqual(errors,[]);console.log('Material Add acceptance passed. Screenshots:',out);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
