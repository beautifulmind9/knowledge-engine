// Synthetic source-detail state coverage. No request reaches a real AI provider.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||'/tmp/ke-source-detail-step3b-review';
fs.mkdirSync(out,{recursive:true});

const source={id:'s1',title:'Facilitator field guide',author:'A. Example',library_id:'l1',file_path:'/private/s1.pdf',file_name:'facilitator-field-guide.pdf',file_type:'.pdf',chunks_path:'/private/s1-parts.json',processing_status:'legacy failure'};
const evidence='Leave a short pause after each exercise so participants can name what changed.';
const units={source_id:'s1',items:[{canonical_asset:{id:'asset-secret',source_id:'source-secret',chunk_id:'chunk-secret',title:'Make room for reflection',what_it_says:'A brief pause gives people time to connect practice with learning.',evidence,chapter_or_section:'After each exercise'},evidence_trail:[{asset_id:'asset-secret',source_id:'source-secret',chunk_id:'chunk-secret',chapter_or_section:'After each exercise',evidence}]}]};
for(const [index,title,summary,quote] of [
 [1,'Give everyone an entry point','Start with a small individual reflection before asking the group to contribute.','Begin with a minute of individual reflection.'],
 [2,'Turn ideas into small experiments','Ask participants to try one change they can observe and discuss.','Try one small change and compare what happened.'],
 [3,'Close with a concrete next step','End with a specific action that carries learning into everyday work.','Name one action to take after the workshop.'],
])units.items.push({canonical_asset:{id:'synthetic-'+index,title,what_it_says:summary},evidence_trail:[{chapter_or_section:'Facilitation practice',evidence:quote}]});
const audit={overlap_rate:.1,superseded_assets:[],old_schema_assets:[],missing_evidence:[],missing_keywords:[],evidence_needing_review:[],asset_types:{insight:1},confidence_distribution:{4:1},asset_count:1,knowledge_unit_count:1,jobs:[{id:'job-secret',chunk_id:'chunk-secret',status:'failed',error:'synthetic diagnostic only'}],note:'Synthetic technical audit.'};
function facts({readiness='ready',usable=true,attention=null,operation='idle',recoveryAllowed=false,readState='read',fileState='available',replacementAllowed=false,completed=20,total=20}={}){
 return {source_id:'s1',readiness,completed_parts:completed,total_parts:total,coverage_text:Number.isInteger(completed)&&Number.isInteger(total)&&total>0?`${completed} of ${total} parts ready`:null,has_usable_knowledge:usable,operation,attention_category:attention,attention_message:attention==='build_stopped'?'The previous knowledge-building attempt stopped before completion.':attention==='build_unconfirmed'?'Previous build has not reported completion.':attention==='ocr_required'?'This PDF has no extractable text. OCR is not supported; supply a PDF with selectable text or another supported file.':attention==='read_failed'?'This file could not be read. Try reading again or supply a readable file.':attention==='artifact_unavailable'?'Source data is unavailable. Restore the source data to continue.':null,file_state:fileState,file_replacement_allowed:replacementAllowed,read_state:readState,next_action:operation==='build_unconfirmed'?'wait_or_reset':readiness==='added'?(fileState==='unattached'?'attach_file':readState==='read'?'read_source':'supply_readable_file'):readiness==='ready_to_build'?'build_knowledge':readiness==='partly_ready'?'continue_building':readiness==='unknown'?'restore_source':'use_knowledge',recovery:recoveryAllowed?[{job_id:'job-secret',category:operation==='build_unconfirmed'?'unconfirmed_build':'failed_build',allowed:true,eligible_at:null}]:[]};
}
const waitProgress=(page,completed,total)=>page.waitForFunction(({completed,total})=>{const p=document.querySelector('#processing-status progress');return p&&Math.abs(p.value-100*completed/total)<1;},{completed,total});

(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),errors=[];
 async function fixture({summary=facts(),mobile=false,withUnits=true,advancedFail=false,sourceState={},usage={configured:true,free_tier_confirmed:true,calls_today:0,daily_call_limit:450,paused:false,daily_limit_reached:false},holdAt=0,failAt=0,provider503At=0,timeoutAt=0,transportAt=0,quotaAt=0,statusFailAt=0,deleteConflict=false,deleteFailure=false}={}){
  const material={...source,...sourceState};
  const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:mobile,hasTouch:mobile});
  page.on('pageerror',error=>errors.push(error.message));const requests=[],dispatchedParts=[];let releasePart,partRequests=0,nextPart=summary.completed_parts||0,inFlight=0,peak=0;const held=new Promise(resolve=>releasePart=resolve);
  await page.route('http://ke.test/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method();let data;
   if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
   requests.push({path:p,query:url.search,method});
   if(p==='/libraries')data={items:[{id:'l1',name:'Workshop notes'}]};
   else if(p==='/sources/s1'&&method==='DELETE'){
    if(deleteFailure)return route.fulfill({status:503,json:{detail:'private storage error'}});
    if(deleteConflict&&!url.searchParams.has('delete_outputs'))return route.fulfill({status:409,json:{detail:"Saved output histories contain this source's knowledge. Set delete_outputs=true to delete those histories too, or keep the source."}});
    data={deleted_source_id:'s1',deleted_output_histories:url.searchParams.has('delete_outputs')?1:0};
   }
   else if(p==='/sources/s1')data=material;
   else if(p==='/sources/s1/identity'&&method==='PUT'){Object.assign(material,request.postDataJSON(),{title_origin:'user_confirmed',author_origin:'user_confirmed'});data=material;}
   else if(p==='/sources/s1/summary'){if(statusFailAt&&partRequests===statusFailAt)return route.fulfill({status:503,json:{detail:'Status unavailable'}});data=summary;}
   else if(p==='/sources/summaries')data=[summary];
   else if(p==='/sources/s1/knowledge-units')data=withUnits?units:{source_id:'s1',items:[]};
   else if(p==='/usage')data=usage;
   else if(p==='/sources/s1/audit'){if(advancedFail)return route.fulfill({status:503,json:{detail:'synthetic diagnostics failure'}});data=audit;}
   else if(p==='/sources/s1/chunks'){if(advancedFail)return route.fulfill({status:503,json:{detail:'synthetic diagnostics failure'}});data={items:[{id:'chunk-secret',chunk_index:1,word_count:340,chapter_or_section:'Practice'}]};}
   else if(p==='/sources')data={items:[material]};
   else if(p==='/outputs/modes')data={items:[{id:'knowledge_answer',label:'Knowledge answer'}]};
   else if(p==='/knowledge-assets/search')data={items:[],count:0};
   else if(p==='/workshops/generate')data={output:{title:'Grounded answer',content:'A pause allows participants to name what changed.',applied_knowledge:[],design_choices:[]},knowledge_snapshot:[],knowledge_unit_count:1};
   else if(p==='/knowledge-extractions/job-secret/recover')data={status:'pending_ai'};
   else if(p.endsWith('/process'))data={message:'Read'};
   else if(p.endsWith('/interpret')){
    assert.equal(url.searchParams.get('max_chunks'),'1');assert.equal(method,'POST');partRequests++;dispatchedParts.push(nextPart);inFlight++;peak=Math.max(peak,inFlight);
    try{
     if(partRequests===holdAt)await held;
     if(partRequests===quotaAt){usage.calls_today=usage.daily_call_limit;usage.daily_limit_reached=true;usage.paused=true;}
     if(partRequests===provider503At){
      usage.calls_today++;summary.attention_category='build_stopped';summary.recovery=[{job_id:'job-secret',category:'failed_build',allowed:true}];
      return await route.fulfill({json:{processed_this_run:0,stopped_reason:'Safe synthetic provider interruption',interruption_category:'provider_unavailable'}});
     }
     if(partRequests===timeoutAt){
      usage.calls_today++;summary.attention_category='build_stopped';summary.attention_message='The previous knowledge-building attempt stopped before completion.';summary.recovery=[{job_id:'job-secret',category:'failed_build',allowed:true}];
      return await route.fulfill({json:{processed_this_run:0,stopped_reason:'Synthetic persisted interruption',interruption_category:'request_timed_out'}});
     }
     if(partRequests===failAt||usage.calls_today>=usage.daily_call_limit){
      if(partRequests===failAt)usage.calls_today++;
      summary.attention_category='build_stopped';summary.attention_message='The previous knowledge-building attempt stopped before completion.';summary.recovery=[{job_id:'job-secret',category:'failed_build',allowed:true}];
      return await route.fulfill({json:{processed_this_run:0,stopped_reason:'Synthetic failure details must not appear in normal UI'}});
     }
     usage.calls_today++;usage.daily_limit_reached=usage.calls_today>=usage.daily_call_limit;usage.paused=usage.daily_limit_reached;
     nextPart++;summary.completed_parts++;summary.coverage_text=`${summary.completed_parts} of ${summary.total_parts} parts ready`;summary.has_usable_knowledge=true;summary.attention_category=null;summary.recovery=[];
     summary.readiness=summary.completed_parts===summary.total_parts?'ready':'partly_ready';summary.next_action=summary.readiness==='ready'?'use_knowledge':'continue_building';
     if(partRequests===transportAt)return await route.abort('failed');
     return await route.fulfill({json:{processed_this_run:1}});
    }finally{inFlight--;}
   }
   else if(/^\/sources\/s1\/file$/.test(p))return route.fulfill({status:200,body:'synthetic file'});
   else throw Error(`Unexpected synthetic request ${method} ${p}`);
   return route.fulfill({json:data});
  });
  await page.goto('http://ke.test/#/library/material/s1');await page.getByRole('heading',{name:material.title,exact:true}).waitFor();
  return {page,requests,dispatchedParts,releasePart,peak:()=>peak,shot:name=>(!process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER||new RegExp(process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER).test(name))?page.screenshot({path:path.join(out,name+'.png'),fullPage:true}):undefined};
 }
 async function capture(name,options,open=[]){
  const f=await fixture(options);for(const label of open)await f.page.locator('summary').filter({hasText:label}).click();await f.shot(name);return f;
 }
 try{
  let f;
  const noInternals=async page=>{assert.equal(await page.getByText('Advanced / Developer',{exact:true}).count(),0);assert.ok(!(await page.locator('#main').innerText()).match(/Uses up to|Build remaining|Build knowledge|Continue building|max_chunks|\bparts?\b|\bchunks?\b|\bjobs?\b|\bIDs?\b/i));};
  for(const [name,summary,withUnits] of [
   ['01-awaiting-continuation',facts({readiness:'ready_to_build',usable:false,completed:0,total:6}),false],
   ['02-partly-ready-knowledge',facts({readiness:'partly_ready',completed:12,total:20}),true],
   ['03-ready-knowledge',facts(),true],
   ['04-ready-no-knowledge',facts({usable:false}),false],
   ['05-unknown-existing-knowledge',facts({readiness:'unknown',attention:'artifact_unavailable',completed:null,total:null}),true],
   ['06-ocr-replacement',facts({readiness:'added',usable:false,completed:0,total:0,attention:'ocr_required',readState:'ocr_required',replacementAllowed:true}),false],
  ]){
   f=await fixture({summary,withUnits});await noInternals(f.page);await f.shot(name);
   assert.equal(await f.page.getByRole('button',{name:'Ask this source',exact:true}).count(),summary.has_usable_knowledge?1:0);
   assert.ok(!f.requests.some(r=>/audit|chunks/.test(r.path)));await f.page.close();
  }
  f=await fixture({summary:facts({readiness:'ready_to_build',usable:false,completed:0,total:6}),holdAt:3});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await waitProgress(f.page,2,6);
  await f.page.getByText('Preparing your material',{exact:true}).waitFor();await f.page.getByRole('button',{name:'Ask this source',exact:true}).waitFor();await noInternals(f.page);await f.shot('07-progressively-usable-running');
  await f.page.getByRole('button',{name:'Stop preparation',exact:true}).click();f.releasePart();await f.page.locator('#processing-status .processing-status-label').getByText('Preparation stopped',{exact:true}).waitFor();assert.equal(await f.page.locator('.material-coverage').textContent(),'Partly prepared');assert.ok(await f.page.locator('.material-status').getByText('Existing knowledge remains available.',{exact:true}).count());assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,3);assert.equal(f.peak(),1);await f.shot('08-user-stopped');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),holdAt:2});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await waitProgress(f.page,13,20);
  const firstRun=await f.page.locator('#processing-status').getAttribute('data-run-id');
  for(let i=0;i<6;i++){await f.page.mouse.move(30+i*70,110+i*35);await f.page.locator('.material-idea').first().hover();}
  await f.page.evaluate(()=>scrollTo(0,300));
  const summaryLine=await f.page.locator('.material-idea-summary').first().boundingBox();if(summaryLine){await f.page.mouse.move(summaryLine.x+4,summaryLine.y+5);await f.page.mouse.down();await f.page.mouse.move(summaryLine.x+100,summaryLine.y+5);await f.page.mouse.up();}
  const identity=f.page.locator('.material-identity-edit');await identity.locator('summary').click();await identity.locator('[name=identity_title]').focus();await identity.locator('summary').click();
  const evidenceDisclosure=f.page.locator('.material-evidence summary').first();await evidenceDisclosure.click();await evidenceDisclosure.click();
  await f.page.setViewportSize({width:1180,height:900});await f.page.evaluate(()=>document.querySelector('#main').updateMaterialPreparation());
  assert.equal(await f.page.locator('#processing-status').getAttribute('data-run-id'),firstRun);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,2);
  assert.equal(await f.page.locator('#processing-status').getAttribute('hidden'),null);await f.shot('20-normal-interactions-running');f.releasePart();
  await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,8);assert.equal(f.peak(),1);await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),provider503At:2});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Partly ready',{exact:true}).waitFor();
  await f.page.locator('#processing-status').getByText('The AI service was temporarily unavailable. Your progress is saved.',{exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,2);assert.equal(await f.page.locator('.material-status').getByText('Existing knowledge remains available.',{exact:true}).count(),1);
  assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).isEnabled(),true);assert.ok(await f.page.getByRole('button',{name:'Ask this source',exact:true}).count());await f.shot('21-provider-503-paused');
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();
  assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,9);await f.shot('22-explicit-continuation-ready');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),timeoutAt:2});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Preparation paused',{exact:true}).waitFor();
  await f.page.locator('#processing-status').getByText('The last preparation request did not finish in time.',{exact:true}).waitFor();
  await f.page.locator('.material-status').getByText('Your progress is saved. Existing knowledge remains available.',{exact:true}).waitFor();
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).waitFor();assert.equal(await f.page.getByRole('button',{name:'Check material status',exact:true}).count(),0);
  assert.equal(await f.page.getByRole('button',{name:'Ask this source',exact:true}).count(),1);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,2);await noInternals(f.page);
  await f.shot('35-timeout-paused-with-knowledge');await f.page.reload();await f.page.locator('.material-status').getByText('Preparation paused',{exact:true}).waitFor();
  await f.page.locator('.material-status').getByText('Your progress is saved. Existing knowledge remains available.',{exact:true}).waitFor();
  assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).count(),1);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,2);assert.equal(f.requests.filter(r=>r.path.endsWith('/upload')).length,0);await f.shot('37-timeout-reloaded-paused');
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();
  assert.deepEqual(f.dispatchedParts,[12,13,13,14,15,16,17,18,19]);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,9);await f.shot('39-timeout-explicit-continuation-ready');await f.page.close();
  f=await fixture({summary:facts({readiness:'ready_to_build',usable:false,completed:0,total:6}),timeoutAt:1,withUnits:false});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Preparation paused',{exact:true}).waitFor();
  await f.page.locator('#processing-status').getByText('The last preparation request did not finish in time.',{exact:true}).waitFor();
  await f.page.locator('.material-status').getByText('Your progress is saved.',{exact:true}).waitFor();
  assert.equal(await f.page.getByRole('button',{name:'Ask this source',exact:true}).count(),0);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,1);await noInternals(f.page);await f.shot('36-timeout-before-knowledge');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),mobile:true,timeoutAt:2});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Preparation paused',{exact:true}).waitFor();
  assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).count(),1);assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await noInternals(f.page);await f.shot('40-mobile-timeout-paused');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:75}),usage:{configured:true,free_tier_confirmed:true,calls_today:433,daily_call_limit:450,paused:false,daily_limit_reached:false}});
  await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('#processing-status').getByText('Preparation paused for today',{exact:true}).waitFor();assert.equal(await f.page.locator('.material-status').getByText('Existing knowledge remains available.',{exact:true}).count(),1);assert.equal(await f.page.locator('.material-coverage').textContent(),'Partly prepared');assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,17);assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).isDisabled(),true);await noInternals(f.page);await f.shot('09-allowance-paused');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),failAt:3});await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('#processing-status').getByText('Preparation stopped',{exact:true}).waitFor();await f.page.locator('.material-status').getByText('Existing knowledge remains available.',{exact:true}).waitFor();assert.equal(await f.page.locator('.material-coverage').textContent(),'Partly prepared');assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,3);assert.equal(await f.page.getByRole('button',{name:'Resolve preparation issue',exact:true}).count(),0);await f.shot('10-failure-existing-knowledge');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),transportAt:2});await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('#processing-status').getByText('Preparation needs confirmation',{exact:true}).waitFor();await f.page.locator('.material-status').getByText('The last request could not be confirmed.',{exact:true}).waitFor();await f.page.getByRole('button',{name:'Check material status',exact:true}).waitFor();assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).count(),0);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,2);await f.shot('38-browser-uncertain');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),statusFailAt:2});await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('#processing-status').getByText('Preparation status unavailable',{exact:true}).waitFor();await f.page.locator('.material-status').getByText('Status unavailable',{exact:true}).waitFor();await f.page.getByText('Preparation progress unavailable',{exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,2);await f.shot('19-status-unavailable');await f.page.close();
  f=await fixture({summary:facts({readiness:'ready_to_build',usable:false,completed:0,total:6})});await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,6);assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).count(),0);await f.shot('12-completed');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),mobile:true,holdAt:2});await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await waitProgress(f.page,13,20);await noInternals(f.page);assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.shot('13-mobile-running');await f.page.getByRole('button',{name:'Stop preparation',exact:true}).click();f.releasePart();await f.page.locator('#processing-status .processing-status-label').getByText('Preparation stopped',{exact:true}).waitFor();assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.shot('14-mobile-stopped');await f.page.close();
  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),holdAt:2});await f.page.getByRole('button',{name:'Continue preparing',exact:true}).click();await waitProgress(f.page,13,20);const runId=await f.page.locator('#processing-status').getAttribute('data-run-id');await f.page.getByRole('link',{name:'Knowledge Engine Home',exact:true}).click();await f.page.getByLabel('Your request',{exact:true}).waitFor();assert.equal(await f.page.locator('#processing-status').getAttribute('data-run-id'),runId);f.releasePart();await f.page.waitForFunction(()=>document.querySelector('#processing-status')?.hidden===true);assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,8);await f.page.goBack();await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,8);await f.page.reload();await f.page.locator('.material-status').getByText('Ready',{exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.path.endsWith('/interpret')).length,8);assert.equal(await f.page.locator('#processing-status').isVisible(),false);await f.page.close();
  f=await fixture({summary:facts()});await f.page.getByText('Source & evidence',{exact:true}).first().click();await f.page.getByText(evidence,{exact:true}).waitFor();await f.shot('15-evidence-desktop');assert.ok(!(await f.page.locator('#main').innerText()).includes('asset-secret'));assert.ok(await f.page.locator('.material-knowledge').evaluate(e=>e.getBoundingClientRect().width>600));await f.page.close();
  f=await fixture({summary:facts(),mobile:true});await f.page.getByText('Source & evidence',{exact:true}).first().click();await f.page.getByText('Manage material',{exact:true}).click();assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.shot('16-mobile-evidence-manage');await f.page.close();
  for(const advancedFail of [false,true]){
   f=await fixture({summary:facts(),advancedFail});await f.page.goto('http://ke.test/#/internal/material/s1');await f.page.getByRole('heading',{name:'Material diagnostics',exact:true}).waitFor();assert.ok(!f.requests.some(r=>r.path.endsWith('/audit')));await f.page.getByText('Advanced / Developer',{exact:true}).click();
   await f.page.getByText(advancedFail?'No developer details are available for this material right now.':'Manual knowledge import',{exact:true}).waitFor();await f.shot(advancedFail?'18-support-unavailable':'17-internal-support');await f.page.close();
  }
  for(const allowed of [false,true]){
   f=await fixture({summary:facts({readiness:'partly_ready',attention:allowed?'build_unconfirmed':null,operation:'build_unconfirmed',recoveryAllowed:allowed,completed:12,total:20})});assert.equal(await f.page.getByRole('button',{name:'Resolve preparation issue',exact:true}).count(),allowed?1:0);assert.equal(await f.page.getByRole('button',{name:'Continue preparing',exact:true}).count(),0);await f.page.close();
  }
  f=await fixture({summary:facts(),withUnits:false});await f.page.getByRole('button',{name:'Ask this source',exact:true}).click();await f.page.getByRole('button',{name:'Ask this material',exact:true}).waitFor();assert.equal(f.requests.filter(r=>r.method==='POST').length,0);assert.equal(await f.page.locator('#ke-source-scope').inputValue(),'s1');assert.ok(await f.page.getByRole('button',{name:'Ask this material',exact:true}).evaluate(e=>e.classList.contains('primary')));await f.page.close();
  f=await fixture();await f.page.getByText('Manage material',{exact:true}).click();let confirmed=false;f.page.on('dialog',async dialog=>{confirmed=true;await dialog.accept();});await f.page.getByRole('button',{name:'Delete material',exact:true}).click();await f.page.getByRole('heading',{name:'Your library',exact:true}).waitFor();assert.ok(confirmed);assert.deepEqual(f.requests.filter(r=>r.method==='DELETE').map(r=>r.query),['']);await f.page.close();
  f=await fixture({deleteConflict:true});await f.page.getByText('Manage material',{exact:true}).click();const prompts=[];let resolveSecond;const secondPrompt=new Promise(resolve=>resolveSecond=resolve);f.page.on('dialog',async dialog=>{prompts.push(dialog.message());await dialog.accept();if(prompts.length===2)resolveSecond();});await f.page.getByRole('button',{name:'Delete material',exact:true}).click();await secondPrompt;await f.page.getByRole('heading',{name:'Your library',exact:true}).waitFor();assert.equal(prompts.length,2);assert.match(prompts[1],/saved work uses this material/i);assert.deepEqual(f.requests.filter(r=>r.method==='DELETE').map(r=>r.query),['','?delete_outputs=true']);await f.page.close();
  f=await fixture({deleteConflict:true});await f.page.getByText('Manage material',{exact:true}).click();let promptCount=0,resolveCancelled;const cancelledPrompt=new Promise(resolve=>resolveCancelled=resolve);f.page.on('dialog',async dialog=>{promptCount++;if(promptCount===1)await dialog.accept();else{await dialog.dismiss();resolveCancelled();}});await f.page.getByRole('button',{name:'Delete material',exact:true}).click();await cancelledPrompt;assert.equal(promptCount,2);assert.deepEqual(f.requests.filter(r=>r.method==='DELETE').map(r=>r.query),['']);assert.equal(await f.page.getByRole('heading',{name:'Facilitator field guide',exact:true}).count(),1);await f.page.close();
  f=await fixture({deleteFailure:true});await f.page.getByText('Manage material',{exact:true}).click();f.page.on('dialog',dialog=>dialog.accept());await f.page.getByRole('button',{name:'Delete material',exact:true}).click();await f.page.getByText('This material could not be removed right now. Check its status and try again.',{exact:true}).waitFor();assert.equal(await f.page.getByRole('heading',{name:'Facilitator field guide',exact:true}).count(),1);assert.equal(f.requests.filter(r=>r.method==='DELETE').length,1);await f.page.close();
  f=await fixture({summary:facts({readiness:'added',usable:false,completed:0,total:0,readState:'not_read'}),withUnits:false,sourceState:{title:'Download 1837',author:'',title_origin:'filename',author_origin:'unconfirmed'}});await f.page.getByText('Temporary name from filename',{exact:true}).waitFor();await f.shot('25-identity-provisional');await f.page.getByText('Review identity',{exact:true}).click();await f.page.locator('[name=identity_title]').fill('Triggers');await f.page.locator('[name=identity_author]').fill('Marshall Goldsmith');await f.page.getByRole('button',{name:'Save identity',exact:true}).click();await f.page.getByRole('heading',{name:'Triggers',exact:true}).waitFor();await f.page.getByText('Marshall Goldsmith',{exact:true}).waitFor();await f.page.getByText('Edit identity',{exact:true}).waitFor();assert.equal(await f.page.getByText(/suggested|please check/i).count(),0);await f.page.evaluate(()=>scrollTo(0,0));await f.shot('26-identity-user-confirmed');await f.page.close();
  f=await fixture({sourceState:{title:'Triggers',author:'Marshall Goldsmith',title_origin:'material_text',author_origin:'material_text_suggested'}});await f.page.getByText('Found in the material',{exact:true}).waitFor();await f.page.getByText('Author suggested from the material — please check',{exact:true}).waitFor();await f.page.getByText('Review identity',{exact:true}).waitFor();await f.shot('27-identity-uncertain-author');await f.page.close();
  f=await fixture({sourceState:{title:'Triggers',author:'Marshall Goldsmith',title_origin:'material_text',author_origin:'material_text_suggested'}});await f.page.getByText('Review identity',{exact:true}).click();await f.page.getByRole('button',{name:'Save identity',exact:true}).click();await f.page.getByText('Edit identity',{exact:true}).waitFor();await f.page.getByRole('heading',{name:'Triggers',exact:true}).waitFor();{const identityHeader=await f.page.locator('.material-header').innerText();assert.ok(!/suggested|please check/i.test(identityHeader),JSON.stringify({identityHeader,requests:f.requests.slice(-8)}))}await f.shot('29-identity-author-confirmed');await f.page.close();
  f=await fixture({sourceState:{title:'Triggers',author:'Marshall Goldsmith',title_origin:'material_text',author_origin:'material_text_suggested'}});await f.page.getByText('Review identity',{exact:true}).click();await f.page.locator('[name=identity_author]').fill('Marshall Goldsmith (corrected)');await f.page.getByRole('button',{name:'Save identity',exact:true}).click();await f.page.getByText('Edit identity',{exact:true}).waitFor();await f.page.getByText('Marshall Goldsmith (corrected)',{exact:true}).waitFor();assert.equal(await f.page.getByText(/suggested|please check/i).count(),0);await f.shot('30-identity-author-corrected');await f.page.close();
  f=await fixture({sourceState:{title:'Triggers',author:'Marshall Goldsmith',title_origin:'user_confirmed',author_origin:'material_text_suggested'}});await f.page.getByText('Author suggested from the material — please check',{exact:true}).waitFor();assert.equal(await f.page.getByText('Found in the material',{exact:true}).count(),0);await f.shot('31-identity-mixed-confidence');await f.page.close();
  f=await fixture({sourceState:{title:'Triggers',author:'',title_origin:'user_confirmed',author_origin:'user_confirmed'}});assert.equal(await f.page.getByText('Marshall Goldsmith',{exact:true}).count(),0);assert.equal(await f.page.getByText(/author not confirmed|suggested|please check/i).count(),0);assert.equal(await f.page.getByText('Review identity',{exact:true}).count(),0);await f.shot('32-identity-blank-author');await f.page.close();
  f=await fixture({mobile:true,sourceState:{title:'Triggers',author:'Marshall Goldsmith',title_origin:'material_text',author_origin:'material_text_suggested'}});await f.page.getByText('Author suggested from the material — please check',{exact:true}).waitFor();await f.page.evaluate(()=>scrollTo(0,0));await f.shot('33-mobile-identity-suggested');await f.page.close();
  f=await fixture({mobile:true,sourceState:{title:'Triggers',author:'Marshall Goldsmith',title_origin:'material_text',author_origin:'material_text_suggested'}});await f.page.getByText('Review identity',{exact:true}).click();await f.page.getByRole('button',{name:'Save identity',exact:true}).click();await f.page.getByText('Edit identity',{exact:true}).waitFor();assert.equal(await f.page.getByText(/suggested|please check/i).count(),0);await f.page.evaluate(()=>scrollTo(0,0));await f.shot('34-mobile-identity-confirmed');await f.page.close();
  f=await fixture({summary:facts({readiness:'added',usable:false,completed:0,total:0,readState:'not_read'}),withUnits:false,mobile:true,sourceState:{title:'Download 1837',author:'',title_origin:'filename',author_origin:'unconfirmed'}});await f.page.getByText('Review identity',{exact:true}).waitFor();assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.shot('28-mobile-identity');await f.page.close();
  assert.deepEqual(errors,[]);console.log('Source detail acceptance passed: preparation, progressive knowledge, stopping, uncertainty, quota, navigation, support, evidence and mobile. Screenshots:',out);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
