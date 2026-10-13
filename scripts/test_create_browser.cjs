// Deterministic Create review. All API/provider responses are synthetic; no server or credentials.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const screenshots=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||'/tmp/ke-create-review';
fs.mkdirSync(screenshots,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const errors=[];
 const modes=[{id:'writing',label:'Writing / editing',formats:['Email','Essay']},{id:'workshop_plan',label:'Workshop / facilitation plan'},
 {id:'social_content',label:'Content / social media',formats:['LinkedIn post','Carousel']},{id:'knowledge_answer',label:'Knowledge answer / synthesis'}];
 async function fixture(options={}){
  const page=await browser.newPage({viewport:options.mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:!!options.mobile,hasTouch:!!options.mobile}),requests=[],snapshots=new Map();let pending,saved;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://ke.test/**',async route=>{
   const url=new URL(route.request().url()),p=url.pathname,method=route.request().method();
   if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
   const payload=method==='POST'?route.request().postDataJSON():null;
   if(payload)requests.push({path:p,body:payload});
   if(p==='/libraries')return route.fulfill({json:{items:[{id:'l1',name:'Reading'}]}});
   if(p==='/sources')return route.fulfill({json:{items:[{id:'s1',title:'Facilitator notes',library_id:'l1',processing_status:'knowledge_interpreting'}]}});
   if(p==='/outputs/modes')return route.fulfill({json:{items:modes}});
   if(p==='/workshops/prepare'){
    const ideaCount=options.empty?0:options.ideaCount||1;
    const titles=['Practice breaks','Clear goals','Practical activities','Reflection pauses','Peer feedback'];
    const knowledgeUnits=Array.from({length:ideaCount},(_,i)=>({canonical_asset:{id:'a'+(i+1),title:titles[i],what_it_says:i===0?'Use practice breaks to help participants retain learning.':'A synthetic supporting idea for reviewing the complete knowledge preview.'},source_ids:['s1'],evidence_trail:[{source_id:'s1',chunk_id:'c1',evidence:i===0?'Use practice breaks.':'Synthetic evidence for '+titles[i]+'.'}]}));
    const id='server-evidence-snapshot-'+snapshots.size;
    const evidence={prepared_snapshot_id:id,interaction_revision:payload.interaction_revision,knowledge_unit_count:ideaCount,
     knowledge_units:knowledgeUnits,
     source_coverage:options.empty?[]:[{source_id:'s1',title:'Facilitator notes',prepared_sections:12,total_sections:20,relevant_idea_count:ideaCount}],
     synthesis_context:{agreements:[],tensions:[],limitations:'Deterministic lexical signals only.'}};
    snapshots.set(id,{payload,evidence});
    const deliver=()=>route.fulfill(options.failPrepare?{status:422,json:{detail:'Synthetic preparation failure'}}:{json:evidence});
    if(options.delayPrepare){pending=deliver;return;}return deliver();
   }
   if(p==='/workshops/generate'){
    const snapshot=snapshots.get(payload.prepared_snapshot_id);assert.ok(snapshot,'Generation must name a reviewed snapshot');
    const {prepared_snapshot_id,...brief}=payload;assert.deepEqual(brief,snapshot.payload,'Exact reviewed request/revision');
    if(options.failGenerate)return route.fulfill({status:502,json:{detail:'Synthetic generation failure — no retry'}});
    saved={id:'o1',title:'Grounded draft',content:'A practical draft using practice breaks. The sequence is a drafting choice, not a claim from the source.',version:1,created_at:'2026-10-11',output_type:payload.output_type,provider:'mock',model:'deterministic',applied_knowledge:[{asset_id:'a1',usage_note:'Practice breaks shape the plan.'}],design_choices:['The sequence is a generated design choice.'],knowledge_snapshot:snapshot.evidence.knowledge_units};
    return route.fulfill({json:{saved_output:{id:'o1'}}});
   }
   if(p==='/outputs/o1')return route.fulfill({json:saved});
   if(p.endsWith('/quality'))return route.fulfill({json:{validation_status:'needs_review',issues:[],note:'Human review required.'}});
   return route.fulfill({json:{items:[],count:0}});
  });
  await page.goto('http://ke.test/#/create');await page.getByLabel('What would you like').waitFor();
  return {page,requests,release:async()=>{assert.ok(pending);await pending();},fill:async text=>{
   const input=page.locator('[name=original_request]');if(!await input.isVisible())await page.getByText('Your original request · Edit',{exact:true}).click();await input.fill(text);
  },review:async()=>{await page.getByRole('button',{name:'Continue',exact:true}).click();await page.getByRole('heading',{name:'Here’s what I understood'}).waitFor();},ready:async()=>page.getByRole('heading',{name:options.ideaCount?`${options.ideaCount} relevant ideas found`:'1 relevant idea found',exact:true}).waitFor(),shot:async name=>page.screenshot({path:path.join(screenshots,name+'.png'),fullPage:true})};
 }
 try{
  let f=await fixture();
  assert.equal(await f.page.locator('#create-brief textarea').count(),1);assert.equal(await f.page.locator('[name=goal]').count(),0);
  assert.doesNotMatch(await f.page.locator('main').innerText(),/Gemini|JSON|manual import|one attempt|tab until/);
  await f.shot('01-natural-request');await f.fill('Help me think about better meetings');assert.equal(f.requests.length,0);await f.review();
  assert.equal(f.requests.length,0);assert.equal(await f.page.locator('[name=output_type]').inputValue(),'');await f.shot('02-vague-request');
  await f.page.locator('[name=output_type]').selectOption('writing');await f.ready();assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
  await f.page.close();console.log('PASS vague request: asks locally for result; no arbitrary family or provider call');

  f=await fixture();const brief='Design a 90 minute workshop for new managers.\nKeep a long reflection break. Do not use role play. Work without slides. Budget: under $200.\nAudience: team leads';
  await f.fill(brief);await f.review();await f.ready();
  assert.equal(f.requests[0].body.situation,brief);assert.equal(f.requests[0].body.output_type,'workshop_plan');
  const normal=await f.page.locator('main').innerText();assert.match(normal,/Facilitator notes · Partly prepared/);assert.doesNotMatch(normal,/sections ready|\bparts? ready\b/i);
  assert.doesNotMatch(normal,/asset_id|chunk_id|retrieval_query|schema|Pydantic|Goal|Audience: team leads|Ctrl|Command|All materials|Refresh/);
  assert.equal(await f.page.locator('[name=original_request]').isVisible(),false);
  assert.equal(await f.page.locator('[name=audience]').isVisible(),false);
  assert.equal(await f.page.getByRole('button',{name:'Create workshop / facilitation plan',exact:true}).isVisible(),true);
  assert.match(normal,/Source coverage/);assert.match(normal,/Uses the knowledge shown above/);assert.doesNotMatch(normal,/drafting attempt/);
  await f.shot('03-professional-brief');
  const evidence=await f.page.locator('.knowledge-preview').boundingBox(),action=await f.page.locator('.create-final').boundingBox();
  assert.ok(action.y>evidence.y+evidence.height);
  await f.page.locator('#create-brief').screenshot({path:path.join(screenshots,'10-coverage-current-knowledge.png')});
  await f.page.getByText('Adjust details',{exact:true}).click();await f.page.locator('[name=task]').press('Enter');
  assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);await f.page.getByText('Adjust details',{exact:true}).click();
  await f.page.getByRole('button',{name:/^Create /,exact:false}).click();await f.page.getByRole('heading',{name:'Grounded draft',exact:true}).waitFor();
  assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,1);assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
  await f.shot('04-saved-grounded-output');await f.page.close();console.log('PASS concise professional brief, real coverage shape, exact snapshot and saved output');

  f=await fixture({mobile:true,ideaCount:5});await f.fill('Write a personal birthday essay. Preserve the handheld feeling and long pauses. Avoid polished language. Direction: intimate and imperfect');await f.review();await f.ready();
  await f.page.getByText('Adjust details',{exact:true}).click();await f.page.locator('[name=preserve]').fill('Keep my voice and final pause');
  assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,1);
  await f.page.locator('[name=preserve]').blur();await f.page.getByRole('button',{name:/^Create /,exact:false}).waitFor();
  assert.equal(f.requests.filter(r=>r.path==='/workshops/prepare').length,2);assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,0);
  await f.page.getByText('Search scope · Across your library',{exact:true}).click();await f.page.getByRole('checkbox',{name:'Facilitator notes',exact:true}).check();await f.ready();
  assert.deepEqual(f.requests.filter(r=>r.path==='/workshops/prepare').at(-1).body.source_ids,['s1']);
  await f.page.getByText('Search scope · Facilitator notes',{exact:true}).click();await f.page.getByText('Adjust details',{exact:true}).click();
  await f.page.getByRole('button',{name:'My work',exact:true}).click();await f.page.getByRole('button',{name:'Create',exact:true}).click();await f.ready();
  assert.equal(await f.page.locator('[name=preserve]').inputValue(),'Keep my voice and final pause');
  assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.equal(await f.page.locator('.preview-idea:visible').count(),2);
  assert.equal(await f.page.getByRole('button',{name:'Create essay',exact:true}).isVisible(),true);
  const beforeExpansion=f.requests.length;
  await f.page.getByRole('button',{name:'View all 5 ideas',exact:true}).click();assert.equal(await f.page.locator('.preview-idea:visible').count(),5);
  await f.page.getByRole('button',{name:'Show fewer ideas',exact:true}).click();assert.equal(await f.page.locator('.preview-idea:visible').count(),2);assert.equal(f.requests.length,beforeExpansion);
  await f.shot('05-creative-mobile');
  await f.page.getByRole('button',{name:/^Create /,exact:false}).click();await f.page.getByRole('heading',{name:'Grounded draft',exact:true}).waitFor();
  assert.deepEqual(f.requests.find(r=>r.path==='/workshops/generate').body.preserve,['Keep my voice and final pause']);await f.page.close();console.log('PASS bounded mobile preview, all-idea inspection, full snapshot, scope selection and fit');

  f=await fixture();await f.fill('Write an essay from the leadership book.');await f.review();assert.equal(f.requests.length,0);
  await f.page.locator('.clarification').getByText('Needs your input', {exact:false}).waitFor();await f.shot('06-ambiguous-material');
  await f.page.getByRole('button',{name:'Search across your library',exact:true}).click();await f.ready();
  assert.deepEqual(f.requests[0].body.source_ids,[]);assert.equal(f.requests.length,1);await f.page.close();console.log('PASS unresolved scope blocks retrieval; local choice updates knowledge without Refresh');

  f=await fixture();await f.fill(' ');await f.page.getByRole('button',{name:'Continue',exact:true}).click();await f.page.getByText('Tell us a little',{exact:false}).waitFor();assert.equal(f.requests.length,0);await f.shot('07-local-interpretation-failure');await f.page.close();console.log('PASS empty request makes no call');

  f=await fixture({failPrepare:true});await f.fill('Write an essay. Preserve my voice.');await f.review();await f.page.getByText('Synthetic preparation failure',{exact:false}).waitFor();assert.equal(f.requests.length,1);assert.equal(await f.page.locator('.create-final button').isVisible(),false);await f.page.close();console.log('PASS preparation failure blocks Create, no automatic retry');

  f=await fixture({failGenerate:true});await f.fill('Write an essay. Preserve my voice.');await f.review();await f.ready();await f.page.getByRole('button',{name:/^Create /,exact:false}).click();await f.page.getByText('Synthetic generation failure',{exact:false}).waitFor();assert.equal(f.requests.filter(r=>r.path==='/workshops/generate').length,1);await f.shot('08-generation-failure');await f.page.close();console.log('PASS generation failure: no retry, repair or fallback');

  f=await fixture({delayPrepare:true});await f.fill('Write an old essay.');await f.review();await f.fill('Write a newer essay without jargon.');await f.release();await f.page.waitForTimeout(100);
  assert.equal(await f.page.locator('[name=original_request]').inputValue(),'Write a newer essay without jargon.');assert.equal(await f.page.getByRole('heading',{name:'1 relevant idea found'}).count(),0);assert.equal(await f.page.locator('.create-final button').isVisible(),false);await f.shot('09-pending-request-edit');await f.page.close();console.log('PASS edits during pending preparation suppress old result');

  f=await fixture({empty:true});await f.fill('Write about a distant topic.');await f.review();await f.page.getByRole('heading',{name:'0 relevant ideas found'}).waitFor();assert.equal(await f.page.locator('.create-final button').isVisible(),false);assert.doesNotMatch(await f.page.locator('main').innerText(),/insufficient evidence/);await f.page.close();console.log('PASS zero results reported factually; no adequacy claim or provider call');
  f=await fixture({ideaCount:5});await f.fill('Write an essay.');await f.review();await f.ready();
  assert.equal(await f.page.locator('.preview-idea:visible').count(),5);assert.equal(await f.page.getByRole('button',{name:'View all 5 ideas'}).isVisible(),false);
  await f.page.close();console.log('PASS desktop continues to show all retrieved ideas');
  assert.deepEqual(errors,[]);console.log('10 browser scenarios passed; zero runtime errors and real Gemini calls. Screenshots:',screenshots);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
