// Synthetic end-to-end batch preparation coverage; no real provider requests.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||path.join(root,'outputs/library-batch-review');fs.mkdirSync(out,{recursive:true});
const titles=['Marketing Made Simple','The Choice Factory','Triggers','Hooked','Made to Stick','Influence'];
const summary=(s)=>({source_id:s.id,readiness:s.completed===s.total?'ready':s.completed?'partly_ready':'ready_to_build',completed_parts:s.completed,total_parts:s.total,coverage_text:`${s.completed} of ${s.total} parts ready`,has_usable_knowledge:s.completed>0,operation:'idle',attention_category:s.attention?'build_stopped':null,attention_message:s.attention?'The previous attempt stopped before completion.':null,file_state:'available',read_state:'read',next_action:s.completed===s.total?'use_knowledge':s.completed?'continue_building':'build_knowledge',recovery:[]});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),page=await browser.newPage({viewport:{width:1680,height:1100}}),errors=[],sources=[],calls=[],attempts=new Map();
 let allowance=450,used=0,release,signal;const gate=new Promise(r=>release=r),started=new Promise(r=>signal=r);let holdFirst=true,failMaterialTwo=true;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://ke.test/**',async route=>{
  const request=route.request(),url=new URL(request.url()),p=url.pathname,method=request.method(),body=method==='POST'&&!p.endsWith('/upload')?request.postDataJSON():null;calls.push({path:p,method});let data;
  if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
  if(p==='/libraries'&&method==='GET')data={items:[{id:'l1',name:'My Library'}]};
  else if(p==='/sources'&&method==='GET')data={items:sources};
  else if(p==='/sources'&&method==='POST'){data={id:`s${sources.length+1}`,...body,processing_status:'created'};sources.push({...data,completed:0,total:2,usable:false,attention:false});}
  else if(p==='/sources/summaries')data=sources.map(summary);
  else if(p==='/usage')data={configured:true,free_tier_confirmed:true,daily_call_limit:allowance,calls_today:used,daily_limit_reached:used>=allowance,paused:false};
  else if(p.endsWith('/upload')){const s=sources.find(item=>p.includes(`/${item.id}/`));s.file_path='synthetic-file';data={ok:true};}
  else if(p.endsWith('/process')){const s=sources.find(item=>p.includes(`/${item.id}/`));s.chunks_path='synthetic-parts';data={ok:true};}
  else if(p.endsWith('/interpret')){
   const s=sources.find(item=>p.includes(`/${item.id}/`));assert.equal(url.searchParams.get('max_chunks'),'1');signal();if(holdFirst){holdFirst=false;await gate;}
   const attempt=(attempts.get(s.id)||0)+1;attempts.set(s.id,attempt);used++;
   if(s.id==='s2'&&attempt===1&&failMaterialTwo){s.attention=true;return route.fulfill({status:503,json:{detail:'Synthetic provider interruption'}});}
   s.completed++;s.usable=true;s.attention=false;data={processed_this_run:1};
  }
  else if(p.endsWith('/summary')){const s=sources.find(item=>p.includes(`/${item.id}/`));data=summary(s);}
  else if(/^\/sources\/[^/]+$/.test(p)){data=sources.find(item=>item.id===p.split('/').at(-1));}
  else if(p.endsWith('/knowledge-units'))data={items:[]};
  else if(p==='/outputs/modes')data={items:[]};
  else if(p==='/outputs')data={items:[],count:0};
  else if(p==='/data/integrity')data={ok:true,issues:[]};
  else throw Error(`Unexpected synthetic API ${method} ${p}`);
  return route.fulfill({json:data});
 });
 try{
  await page.goto('http://ke.test/#/library?add=1');await page.locator('#material-add input[type=file]').waitFor();
  const files=titles.map((title,i)=>({name:`${title.replaceAll(' ','_')}.pdf`,mimeType:'application/pdf',buffer:Buffer.from(`synthetic ${i}`)}));
  await page.locator('#material-add input[name=file]').setInputFiles(files);await page.getByRole('button',{name:'Add 6 materials',exact:true}).click();await started;
  const activeRun=await page.locator('#processing-status').getAttribute('data-run-id');
  await page.getByRole('button',{name:'Library',exact:true}).click();await page.getByRole('heading',{name:'Your library',exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('.library-row-readiness').length===6&&[...document.querySelectorAll('.library-row-readiness')].some(e=>e.textContent==='Preparing'));
  assert.equal(await page.locator('.library-rows').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),3);await page.screenshot({path:path.join(out,'04-multi-material-preparing-wide.png'),fullPage:true});
  await page.getByRole('button',{name:'Create',exact:true}).click();await page.getByRole('heading',{name:'What are you working on?',exact:true}).waitFor();assert.equal(await page.locator('#processing-status').getAttribute('data-run-id'),activeRun);assert.equal(calls.filter(c=>c.path.endsWith('/interpret')).length,1);await page.screenshot({path:path.join(out,'14-create-while-library-prepares.png'),fullPage:true});
  await page.getByRole('button',{name:'My work',exact:true}).click();await page.getByRole('heading',{name:'Work worth coming back to.',exact:true}).waitFor();assert.equal(await page.locator('#processing-status').getAttribute('data-run-id'),activeRun);assert.equal(calls.filter(c=>c.path.endsWith('/interpret')).length,1);await page.screenshot({path:path.join(out,'15-my-work-while-library-prepares.png'),fullPage:true});
  await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('heading',{name:'Your data, in your hands.',exact:true}).waitFor();assert.equal(await page.locator('#processing-status').getAttribute('data-run-id'),activeRun);assert.equal(calls.filter(c=>c.path.endsWith('/interpret')).length,1);
  await page.getByRole('button',{name:'Library',exact:true}).click();await page.getByRole('heading',{name:'Your library',exact:true}).waitFor();assert.equal(await page.locator('#processing-status').getAttribute('data-run-id'),activeRun);
  await page.getByRole('button',{name:'Open material',exact:true}).nth(1).click();await page.getByRole('heading',{name:'The Choice Factory',exact:true}).waitFor();assert.equal(await page.locator('#processing-status').isVisible(),true);await page.getByRole('button',{name:'Library',exact:true}).click();await page.locator('.library-row').first().waitFor();
  await page.locator('.library-row').first().getByRole('button',{name:'Open material',exact:true}).click();await page.getByRole('heading',{name:'Marketing Made Simple',exact:true}).waitFor();assert.equal(await page.locator('#processing-status').getAttribute('data-run-id'),activeRun);assert.equal(await page.locator('.material-status').getByText('Preparing',{exact:true}).count(),1);await page.screenshot({path:path.join(out,'16-return-to-preparing-material.png'),fullPage:true});
  await page.getByRole('button',{name:'Library',exact:true}).click();await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));assert.equal(await page.locator('#processing-status').isVisible(),true);assert.equal(await page.getByRole('button',{name:'Stop preparation',exact:true}).isVisible(),true);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'17-mobile-global-preparation.png'),fullPage:true});await page.setViewportSize({width:1680,height:1100});
  await page.locator('.library-row').first().hover();await page.mouse.move(120,740);await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  release();await page.getByText('5 materials are ready. 1 material needs another attempt.',{exact:true}).waitFor();await page.screenshot({path:path.join(out,'06-batch-partial-failure.png'),fullPage:true});
  assert.equal(await page.locator('#processing-status .processing-status-label').textContent(),'Batch attempt complete');assert.match(await page.locator('#processing-status').innerText(),/Completed progress is saved/);assert.doesNotMatch(await page.locator('#processing-status').innerText(),/need another attempt/);assert.equal(await page.getByRole('button',{name:'Stop preparation'}).count(),0);
  assert.equal(attempts.get('s2'),1);assert.deepEqual(sources.slice(2).map(s=>s.completed),[2,2,2,2]);
  await page.setViewportSize({width:900,height:1000});assert.equal(await page.locator('.library-rows').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),2);await page.screenshot({path:path.join(out,'08-library-tablet.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('.library-rows').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),1);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'09-library-mobile.png'),fullPage:true});
  await page.getByRole('button',{name:'Continue incomplete materials',exact:true}).click();await page.waitForFunction(()=>{const r=document.querySelector('#processing-status');return r&&!r.hidden&&r.querySelector('.processing-status-label')?.textContent==='Preparing your material';});await page.waitForFunction(()=>document.querySelector('#processing-status')?.hidden===true);assert.equal(attempts.get('s2'),3);assert.ok(sources.every(s=>s.completed===2));
  assert.ok(!(await page.locator('body').innerText()).match(/chunk|asset_id|provider call|AI action/i));await page.screenshot({path:path.join(out,'07-batch-completed-after-continuation.png'),fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  console.log(`Multi-material browser acceptance passed: ${sources.length} materials, one isolated 503, explicit continuation, sequential dispatch. Screenshots: ${out}`);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
