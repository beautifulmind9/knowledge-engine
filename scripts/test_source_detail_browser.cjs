// Synthetic source-detail state coverage. No request reaches a real AI provider.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||'/tmp/ke-source-detail-step3b-review';
fs.mkdirSync(out,{recursive:true});

const source={id:'s1',title:'Facilitator field guide',author:'A. Example',library_id:'l1',file_path:'/private/s1.pdf',file_name:'facilitator-field-guide.pdf',file_type:'.pdf',chunks_path:'/private/s1-parts.json',processing_status:'legacy failure'};
const evidence='Leave a short pause after each exercise so participants can name what changed.';
const units={source_id:'s1',items:[{canonical_asset:{id:'asset-secret',source_id:'source-secret',chunk_id:'chunk-secret',title:'Make room for reflection',what_it_says:'A brief pause gives people time to connect practice with learning.',evidence,chapter_or_section:'After each exercise'},evidence_trail:[{asset_id:'asset-secret',source_id:'source-secret',chunk_id:'chunk-secret',chapter_or_section:'After each exercise',evidence}]}]};
const audit={overlap_rate:.1,superseded_assets:[],old_schema_assets:[],missing_evidence:[],missing_keywords:[],evidence_needing_review:[],asset_types:{insight:1},confidence_distribution:{4:1},asset_count:1,knowledge_unit_count:1,jobs:[{id:'job-secret',chunk_id:'chunk-secret',status:'failed',error:'synthetic diagnostic only'}],note:'Synthetic technical audit.'};
function facts({readiness='ready',usable=true,attention=null,operation='idle',recoveryAllowed=false,readState='read',fileState='available',replacementAllowed=false,completed=20,total=20}={}){
 return {source_id:'s1',readiness,completed_parts:completed,total_parts:total,coverage_text:Number.isInteger(completed)&&Number.isInteger(total)&&total>0?`${completed} of ${total} parts ready`:null,has_usable_knowledge:usable,operation,attention_category:attention,attention_message:attention==='build_stopped'?'The previous knowledge-building attempt stopped before completion.':attention==='build_unconfirmed'?'Previous build has not reported completion.':attention==='ocr_required'?'This PDF has no extractable text. OCR is not supported; supply a PDF with selectable text or another supported file.':attention==='read_failed'?'This file could not be read. Try reading again or supply a readable file.':attention==='artifact_unavailable'?'Source data is unavailable. Restore the source data to continue.':null,file_state:fileState,file_replacement_allowed:replacementAllowed,read_state:readState,next_action:readiness==='added'?(fileState==='unattached'?'attach_file':readState==='read'?'read_source':'supply_readable_file'):readiness==='ready_to_build'?'build_knowledge':readiness==='partly_ready'?'continue_building':readiness==='unknown'?'restore_source':'use_knowledge',recovery:recoveryAllowed?[{job_id:'job-secret',category:'failed_build',allowed:true,eligible_at:null}]:[]};
}

(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),errors=[];
 async function fixture({summary=facts(),mobile=false,withUnits=true,advancedFail=false,sourceState={}}={}){
  const material={...source,...sourceState};
  const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:mobile,hasTouch:mobile});
  page.on('pageerror',error=>errors.push(error.message));const requests=[];
  await page.route('http://ke.test/**',async route=>{
   const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method();let data;
   if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
   requests.push({path:p,method});
   if(p==='/libraries')data={items:[{id:'l1',name:'Workshop notes'}]};
   else if(p==='/sources/s1'&&method==='DELETE')data={deleted_source_id:'s1',deleted_output_histories:1};
   else if(p==='/sources/s1')data=material;
   else if(p==='/sources/s1/summary')data=summary;
   else if(p==='/sources/s1/knowledge-units')data=withUnits?units:{source_id:'s1',items:[]};
   else if(p==='/sources/s1/audit'){if(advancedFail)return route.fulfill({status:503,json:{detail:'synthetic diagnostics failure'}});data=audit;}
   else if(p==='/sources/s1/chunks'){if(advancedFail)return route.fulfill({status:503,json:{detail:'synthetic diagnostics failure'}});data={items:[{id:'chunk-secret',chunk_index:1,word_count:340,chapter_or_section:'Practice'}]};}
   else if(p==='/sources')data={items:[material]};
   else if(p==='/outputs/modes')data={items:[{id:'knowledge_answer',label:'Knowledge answer'}]};
   else if(p==='/knowledge-assets/search')data={items:[],count:0};
   else if(p==='/workshops/generate')data={output:{title:'Grounded answer',content:'A pause allows participants to name what changed.',applied_knowledge:[],design_choices:[]},knowledge_snapshot:[],knowledge_unit_count:1};
   else if(p==='/knowledge-extractions/job-secret/recover')data={status:'pending_ai'};
   else if(p.endsWith('/process'))data={message:'Read'};
   else if(p.includes('/interpret'))data={processed_this_run:1};
   else if(/^\/sources\/s1\/file$/.test(p))return route.fulfill({status:200,body:'synthetic file'});
   else throw Error(`Unexpected synthetic request ${method} ${p}`);
   return route.fulfill({json:data});
  });
  await page.goto('http://ke.test/#/library/material/s1');await page.getByRole('heading',{name:material.title,exact:true}).waitFor();
  return {page,requests,shot:name=>(!process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER||new RegExp(process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER).test(name))?page.screenshot({path:path.join(out,name+'.png'),fullPage:true}):undefined};
 }
 async function capture(name,options,open=[]){
  const f=await fixture(options);for(const label of open)await f.page.locator('summary').filter({hasText:label}).click();await f.shot(name);return f;
 }
 try{
  let f=await capture('01-ready-to-build-no-knowledge',{summary:facts({readiness:'ready_to_build',usable:false,completed:0,total:20})});
  assert.equal(await f.page.getByRole('button',{name:'Build knowledge',exact:true}).count(),1);assert.equal(await f.page.getByRole('button',{name:'Ask this source'}).count(),0);await f.page.close();
  f=await capture('02-partly-ready-usable',{summary:facts({readiness:'partly_ready',completed:12,total:20})});assert.equal(await f.page.getByRole('button',{name:'Ask this source'}).count(),1);assert.equal(await f.page.getByRole('button',{name:'Continue building'}).count(),1);await f.page.close();
  f=await capture('03-partly-ready-attention',{summary:facts({readiness:'partly_ready',attention:'build_stopped',completed:12,total:20})});assert.ok((await f.page.locator('#main').textContent()).includes('Needs attention:'));await f.page.close();
  f=await capture('04-ready-usable',{summary:facts()});assert.equal(await f.page.getByRole('button',{name:'Explore ideas'}).count(),1);await f.page.close();
  f=await capture('05-ready-zero-knowledge',{summary:facts({usable:false}),withUnits:false});assert.ok((await f.page.locator('#main').textContent()).includes('No usable knowledge is available from this material yet.'));assert.equal(await f.page.getByRole('button',{name:'Ask this source'}).count(),0);await f.page.close();
  f=await capture('06-unknown-usable',{summary:facts({readiness:'unknown',usable:true,attention:'artifact_unavailable',completed:null,total:null})});assert.equal(await f.page.getByRole('button',{name:'Ask this source'}).count(),1);assert.ok((await f.page.locator('#main').textContent()).includes('Coverage unavailable'));assert.ok((await f.page.locator('#main').textContent()).includes('Existing knowledge remains available. Restore the source data to continue building knowledge.'));assert.ok(!(await f.page.locator('#main').textContent()).includes('preparation'));await f.page.close();
  f=await capture('07-ocr-replacement',{summary:facts({readiness:'added',usable:false,attention:'ocr_required',readState:'ocr_required',replacementAllowed:true,completed:0,total:0}),sourceState:{chunks_path:null}});const ocrReplacement=f.page.getByRole('button',{name:'Use replacement file'});assert.equal(await ocrReplacement.isDisabled(),true);assert.equal(await f.page.getByRole('button',{name:'Read source'}).count(),0);assert.ok(!(await f.page.locator('.material-status').textContent()).match(/\d+ of \d+ parts ready/));await f.page.locator('.material-primary [name=file]').setInputFiles({name:'readable.txt',mimeType:'text/plain',buffer:Buffer.from('readable content')});assert.equal(await ocrReplacement.isDisabled(),false);await f.page.close();
  f=await capture('08-build-recovery-usable',{summary:facts({readiness:'partly_ready',attention:'build_unconfirmed',operation:'build_unconfirmed',recoveryAllowed:true,completed:12,total:20})});assert.equal(await f.page.getByRole('button',{name:'Resolve build issue'}).count(),1);assert.equal(await f.page.getByRole('button',{name:'Ask this source'}).count(),1);await f.page.close();
  f=await fixture({summary:facts({replacementAllowed:false})});await f.page.locator('summary').filter({hasText:'Manage material'}).click();await f.shot('09-manage-expanded');assert.equal(await f.page.getByRole('link',{name:'Open original file'}).count(),1);assert.equal(await f.page.getByRole('button',{name:'Delete material'}).count(),1);assert.equal(await f.page.getByText('The original file can’t be replaced after knowledge building has started. Add another material to use a different file.',{exact:true}).count(),1);assert.equal(await f.page.getByRole('button',{name:'Use replacement file'}).count(),0);await f.page.close();
  f=await fixture({summary:facts({readiness:'ready_to_build',usable:false,replacementAllowed:true,completed:0,total:20})});await f.page.locator('summary').filter({hasText:'Manage material'}).click();await f.page.locator('summary').filter({hasText:'Replace original file'}).click();const replacementAction=f.page.getByRole('button',{name:'Use replacement file'});assert.equal(await replacementAction.isDisabled(),true);await f.shot('14-manage-unbuilt-replacement-allowed');await f.page.locator('.material-manage [name=file]').setInputFiles({name:'replacement.txt',mimeType:'text/plain',buffer:Buffer.from('selected file')});assert.equal(await replacementAction.isDisabled(),false);await f.page.close();
  f=await capture('10-advanced-expanded',{summary:facts()},['Advanced / Developer']);await f.page.getByText('Internal source ID: s1',{exact:true}).waitFor();assert.ok(f.requests.some(request=>request.path==='/sources/s1/audit'));await f.page.close();
  f=await capture('11-evidence-open',{summary:facts()},['Source & evidence']);assert.ok((await f.page.locator('#main').textContent()).includes(evidence));assert.ok(!(await f.page.locator('#main').textContent()).includes('asset-secret'));await f.page.close();
  f=await capture('12-mobile-partial-usable',{summary:facts({readiness:'partly_ready',completed:12,total:20}),mobile:true});assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.ok(await f.page.getByRole('button',{name:'Ask this source'}).evaluate(e=>e.getBoundingClientRect().height>=44));await f.page.close();
  f=await capture('13-mobile-attention-recovery',{summary:facts({readiness:'partly_ready',attention:'build_stopped',recoveryAllowed:true,completed:12,total:20}),mobile:true});assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.equal(await f.page.getByRole('button',{name:'Resolve build issue'}).count(),1);await f.page.close();

  f=await fixture({summary:facts({readiness:'partly_ready',completed:12,total:20}),withUnits:false});await f.page.getByRole('button',{name:'Ask this source'}).click();await f.page.getByRole('button',{name:'Ask with AI'}).waitFor();assert.equal(f.requests.filter(request=>request.method==='POST').length,0);assert.equal(await f.page.locator('#ke-source-scope').inputValue(),'s1');await f.page.getByRole('button',{name:'Ask with AI'}).click();await f.page.getByText('Grounded answer',{exact:true}).waitFor();assert.equal(f.requests.filter(request=>request.path==='/workshops/generate'&&request.method==='POST').length,1);await f.page.close();
  f=await fixture({summary:facts()});await f.page.locator('summary').filter({hasText:'Manage material'}).click();let confirmed=false;f.page.on('dialog',async dialog=>{confirmed=dialog.type()==='confirm';await dialog.accept();});await f.page.getByRole('button',{name:'Delete material'}).click();assert.ok(confirmed);assert.ok(f.requests.some(request=>request.path==='/sources/s1'&&request.method==='DELETE'));await f.page.close();
  for(const [name,mobile] of [['15-desktop-collapsed-disclosures',false],['16-mobile-collapsed-disclosures',true]]){
   f=await fixture({summary:facts(),mobile});const disclosures=await f.page.locator('.material-evidence > summary, .material-manage > summary, .material-advanced > summary').all();assert.equal(disclosures.length,3);
   assert.ok(await f.page.locator('.material-manage').evaluate(e=>!e.open));assert.ok(await f.page.locator('.material-advanced').evaluate(e=>!e.open));assert.ok(await f.page.locator('.material-evidence').first().evaluate(e=>!e.open));
   for(const summaryElement of disclosures)assert.equal(await summaryElement.evaluate(e=>getComputedStyle(e,'::after').content.includes('⌄')),true);
   assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.shot(name);
   const manageSummary=f.page.locator('.material-manage > summary');await manageSummary.focus();await manageSummary.press('Enter');assert.ok(await f.page.locator('.material-manage').evaluate(e=>e.open));await f.page.close();
  }
  assert.deepEqual(errors,[]);console.log('Source detail acceptance passed. Screenshots:',out);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
