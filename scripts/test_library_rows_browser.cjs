// Synthetic Library states only. This acceptance run never contacts an AI provider.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||'/tmp/ke-library-step3a-review';
fs.mkdirSync(out,{recursive:true});

function source(id,title,author=''){
 return {id,title,author,library_id:'l1',file_path:`/private/${id}.pdf`,chunks_path:`/private/${id}-parts.json`,processing_status:'extraction_failed',stopped_reason:'legacy state must not control Library rows'};
}
function summary(id,readiness,usable,completed,total,{attention=null,operation='idle',fileState='available',nextAction=null}={}){
 return {source_id:id,readiness,completed_parts:completed,total_parts:total,coverage_text:Number.isInteger(completed)&&Number.isInteger(total)&&total>0?`${completed} of ${total} parts ready`:null,
  has_usable_knowledge:usable,operation,attention_category:attention,attention_message:attention==='build_stopped'?'The previous knowledge-building attempt stopped before completion.':attention==='artifact_unavailable'?'Source data is unavailable.':null,
  file_state:fileState,read_state:'read',next_action:nextAction||({added:fileState==='unattached'?'attach_file':'read_source',ready_to_build:'build_knowledge',partly_ready:'continue_building',ready:'use_knowledge',unknown:'restore_source'}[readiness]),recovery:[]};
}

(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),errors=[];
 async function fixture({items=[],libraries=[{id:'l1',name:'Reading'}],mobile=false,summaryFailure=false}={}){
  const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:mobile,hasTouch:mobile});
  page.on('pageerror',e=>errors.push(e.message));const requests=[];
  await page.route('http://ke.test/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method();
   if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
   const payload=method==='POST'?request.postDataJSON():null;requests.push({path:p,method,payload});let data;
   if(p==='/libraries')data={items:libraries};
   else if(p==='/sources'){
    const libraryId=url.searchParams.get('library_id');data={items:items.map(item=>item.source).filter(s=>!libraryId||s.library_id===libraryId)};
   }else if(p==='/sources/summaries'){
    if(summaryFailure)return route.fulfill({status:503,json:{detail:'Synthetic summary service outage'}});
    const libraryId=url.searchParams.get('library_id');data=items.filter(item=>!libraryId||item.source.library_id===libraryId).map(item=>item.summary);
   }else if(p.endsWith('/process'))data={message:'Synthetic deterministic read'};
   else if(p.includes('/interpret'))data={processed_this_run:1,stopped_reason:null};
   else if(p==='/outputs/modes')data={items:[]};
   else if(p==='/outputs')data={items:[],count:0};
   else if(p.endsWith('/summary'))data=items.find(item=>p.includes(item.source.id))?.summary;
   else if(/^\/sources\/[^/]+$/.test(p))data=items.find(item=>item.source.id===p.split('/').at(-1))?.source;
   else if(p.endsWith('/knowledge-units'))data={items:[]};
   else throw Error(`Unexpected API ${method} ${p}`);
   return route.fulfill({json:data});
  });
  await page.goto('http://ke.test/#/library');await page.getByRole('heading',{name:'Your library',exact:true}).waitFor();
  return {page,requests,shot:name=>page.screenshot({path:path.join(out,name+'.png'),fullPage:true})};
 }
 try{
  let f=await fixture({libraries:[],items:[]});await f.shot('01-empty-library');
  assert.equal(await f.page.locator('#material-add').count(),1);assert.equal(await f.page.locator('#material-add').isVisible(),true);
  assert.equal(await f.page.locator('summary').filter({hasText:'Create a library'}).evaluate(e=>e.parentElement.open),false);
  assert.ok(f.page.locator('#library-empty'));assert.equal(f.requests.some(r=>r.method==='POST'),false);await f.page.close();

  const states=[
   ['ready-to-build','Build knowledge',summary('r1','ready_to_build',false,0,20),source('r1','Workshop field guide')],
   ['partly-no-knowledge','Continue building',summary('r2','partly_ready',false,6,20),source('r2','Meeting notes')],
   ['partly-usable','Explore knowledge',summary('r3','partly_ready',true,12,20),source('r3','Facilitator notes','A. Example')],
   ['partly-attention','Explore knowledge',summary('r4','partly_ready',true,12,20,{attention:'build_stopped'}),source('r4','Practice journal')],
   ['ready-usable','Explore knowledge',summary('r5','ready',true,20,20),source('r5','The complete guide')],
   ['ready-zero-ideas','Open material',summary('r6','ready',false,20,20),source('r6','Reference with no usable ideas')],
   ['unknown-usable','Explore knowledge',summary('r7','unknown',true,null,null,{attention:'artifact_unavailable'}),source('r7','Recovered knowledge')],
  ];
  for(const [filename,expectedAction,facts,record] of states){
   f=await fixture({items:[{source:record,summary:facts}]});await f.shot(`${String(states.indexOf(states.find(s=>s[0]===filename))+2).padStart(2,'0')}-${filename}`);
   const row=f.page.locator('.library-row');await row.getByText(facts.readiness==='unknown'?'Status unavailable':facts.readiness==='ready_to_build'?'Ready to build knowledge':facts.readiness==='partly_ready'?'Partly ready':'Ready',{exact:true}).waitFor();
   assert.equal(await row.getByRole('button',{name:'Explore knowledge',exact:true}).count(),facts.has_usable_knowledge?1:0);
   assert.equal(await row.getByRole('button',{name:expectedAction,exact:true}).count(),1);
   assert.equal(await row.getByRole('link',{name:'Open material',exact:true}).count(),expectedAction==='Open material'?0:1);
   if(filename==='ready-zero-ideas')assert.ok((await row.textContent()).includes('No usable knowledge is available from this material yet.'));
   assert.ok(!await row.getByText(record.author||'Your material',{exact:true}).count()||!!record.author);
   assert.ok(!(await row.textContent()).includes(record.id));
   if(facts.attention_category)assert.ok((await row.textContent()).includes('Needs attention:'));
   await f.page.close();
  }
  f=await fixture({mobile:true,items:states.slice(0,6).map(([, ,facts,record])=>({source:record,summary:facts})).concat([{source:source('long','ExtremelyLongUnbrokenFilenameForMobileLibraryWrappingWithoutHorizontalOverflow-'.repeat(2)),summary:summary('long','unknown',false,null,null,{attention:'artifact_unavailable'})}])});
  await f.shot('09-mobile-mixed-library');
  assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  for(const row of await f.page.locator('.library-row').all()){
   assert.equal(await row.locator('.actions .primary').count(),1);
   assert.ok(await row.locator('.actions .primary').evaluate(e=>e.getBoundingClientRect().height>=44));
  }
  await f.page.close();

  f=await fixture({libraries:[{id:'l1',name:'Reading'},{id:'l2',name:'Workshop'}],items:[{source:source('multi','Workshop guide'),summary:summary('multi','ready',true,3,3)}]});
  await f.shot('10-multiple-libraries');assert.equal(await f.page.getByLabel('Filter by library').count(),1);await f.page.close();

  f=await fixture({items:[states[2]&&{source:states[2][3],summary:states[2][2]}]});
  const before=f.requests.filter(r=>r.method==='POST').length;await f.page.getByRole('button',{name:'Explore knowledge',exact:true}).click();
  await f.page.locator('#ke-search-form').waitFor();assert.equal(await f.page.locator('#ke-source-scope').inputValue(),'r3');
  assert.equal(f.requests.filter(r=>r.method==='POST').length,before);assert.deepEqual(f.requests.filter(r=>r.method==='POST'),[]);
  await f.page.goBack();await f.page.locator('.library-row').waitFor();assert.equal(f.requests.filter(r=>r.method==='POST').length,0);await f.page.close();

  f=await fixture({items:[{source:source('unknown','Unknown status'),summary:summary('unknown','ready_to_build',false,0,3)}],summaryFailure:true});
  const row=f.page.locator('.library-row');await row.getByText('Readiness unavailable',{exact:true}).waitFor();assert.ok((await row.textContent()).includes('Coverage unavailable'));assert.equal(await row.getByRole('button',{name:'Open material',exact:true}).count(),1);await f.page.close();
  assert.deepEqual(errors,[]);console.log('Step 3A Library acceptance passed. Screenshots:',out);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
