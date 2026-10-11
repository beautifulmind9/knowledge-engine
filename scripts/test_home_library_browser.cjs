// Slice 2A acceptance: synthetic APIs only. No server, credentials or real provider IO.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),out=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||'/tmp/ke-home-library-2a-refined';
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),errors=[];
 async function fixture(mobile=false){
  const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:mobile,hasTouch:mobile}),requests=[];
  page.on('pageerror',e=>errors.push(e.message));
  const source={id:'s1',title:'Facilitator notes',author:'Sample author',library_id:'l1',file_path:'fixture',chunks_path:'fixture',processing_status:'knowledge_interpreting'};
  const units=Array.from({length:13},(_,i)=>({canonical_asset:{id:'a'+i,title:i?'Practice example '+i:'Practice breaks',what_it_says:'Practice breaks support learning through reflection.',asset_type:i%2?'example':'concept',chapter_or_section:'Practice'},source_ids:['s1'],asset_ids:['a'+i],support_count:1,evidence_trail:[{source_id:'s1',chunk_id:'c1',chapter_or_section:'Practice',evidence:'Allow a break for reflection.'}]}));
  await page.route('http://ke.test/**',async route=>{
   const url=new URL(route.request().url()),p=url.pathname,method=route.request().method();
   if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
   const payload=method==='POST'?route.request().postDataJSON():null;requests.push({path:p,method,payload});
   let data;
   if(p==='/libraries')data={items:[{id:'l1',name:'Reading'}]};
   else if(p==='/sources')data={items:[source]};
   else if(p==='/sources/s1')data=source;
   else if(p.endsWith('/knowledge-units'))data={items:units};
   else if(p==='/knowledge-assets/search')data={items:units.slice(0,3)};
   else if(p==='/outputs/modes')data={items:[{id:'writing',label:'Writing',formats:['Essay']},{id:'knowledge_answer',label:'Knowledge answer'}]};
   else if(p==='/workshops/prepare')data={interaction_revision:payload.interaction_revision,prepared_snapshot_id:'synthetic-prepared-evidence-123',knowledge_unit_count:1,knowledge_units:[units[0]],source_coverage:[{title:source.title,prepared_sections:1,total_sections:3,relevant_idea_count:1}],synthesis_context:{tensions:[]}};
   else if(p==='/workshops/generate'){
    assert.equal(payload.output_type,'knowledge_answer');assert.equal(payload.save,false);
    data={output:{title:'Practice and reflection',content:'Practice breaks give learners time to reflect.',applied_knowledge:[{asset_id:'a0',usage_note:'Supports reflection.'}],design_choices:['A concise synthesis.']},knowledge_unit_count:1,knowledge_snapshot:[units[0]]};
   }else if(p==='/outputs')data={items:[],count:0};
   else throw Error('Unexpected API request '+p);
   return route.fulfill({json:data});
  });
  await page.goto('http://ke.test/#/home');await page.getByLabel('Your request',{exact:true}).waitFor();
  return {page,requests,shots:async name=>(!process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER||name.match(process.env.KNOWLEDGE_ENGINE_SCREENSHOT_FILTER))?page.screenshot({path:path.join(out,name+'.png'),fullPage:true}):undefined,posts:()=>requests.filter(r=>r.method==='POST'),goHome:async()=>{await page.getByRole('link',{name:'Knowledge Engine Home',exact:true}).click();await page.getByLabel('Your request',{exact:true}).waitFor();}};
 }
 try{
  let f=await fixture();
  await f.shots('01-home-initial');assert.equal(await f.page.getByRole('button',{name:'Ask & Explore',exact:true}).evaluate(e=>getComputedStyle(e).backgroundColor),await f.page.getByRole('button',{name:'Create something',exact:true}).evaluate(e=>getComputedStyle(e).backgroundColor));const request='  Write an essay about practice breaks.\nPreserve my voice.  ';
  await f.page.getByLabel('Your request',{exact:true}).fill(request);await f.shots('02-home-request');
  await f.page.getByRole('button',{name:'Ask & Explore',exact:true}).click();await f.page.locator('#ke-ask-card').waitFor();
  assert.equal(await f.page.locator('[name=q]').inputValue(),request);assert.equal(await f.page.locator('[name=knowledge_question]').count(),0);assert.equal(f.posts().length,0);
  assert.equal(await f.page.locator('nav button[data-view=library]').getAttribute('aria-current'),'page');
  assert.deepEqual(await f.page.evaluate(()=>Object.keys(history.state)),['keEntry']);assert.ok(!f.page.url().includes('essay'));
  await f.page.goBack();await f.page.getByLabel('Your request',{exact:true}).waitFor();assert.equal(await f.page.getByLabel('Your request',{exact:true}).inputValue(),request);
  await f.page.getByRole('button',{name:'Create something',exact:true}).click();await f.page.locator('[name=original_request]').waitFor();assert.equal(await f.page.locator('[name=original_request]').inputValue(),request);assert.equal(f.posts().length,0);
  await f.page.getByRole('button',{name:'Continue',exact:true}).click();await f.page.getByRole('heading',{name:'1 relevant idea found',exact:true}).waitFor();
  await f.goHome();await f.page.getByLabel('Your request',{exact:true}).fill('Write a new essay');await f.page.getByRole('button',{name:'Create something',exact:true}).click();await f.page.locator('#create-handoff').waitFor();await f.shots('08-existing-draft-decision');assert.equal(await f.page.locator('#create-handoff .handoff-request').count(),0);
  const before=f.posts().length;await f.page.getByRole('button',{name:'Keep current draft',exact:true}).click();await f.page.getByRole('heading',{name:'1 relevant idea found',exact:true}).waitFor();assert.equal(f.posts().length,before);
  await f.goHome();await f.page.getByRole('button',{name:'Create something',exact:true}).click();await f.page.getByRole('button',{name:'Use new request',exact:true}).click();await f.page.locator('[name=original_request]').waitFor();assert.equal(await f.page.locator('[name=original_request]').inputValue(),'Write a new essay');assert.equal(f.posts().length,before);
  await f.page.close();console.log('PASS exact Home handoffs, reversible routing, local Keep/Replace and unchanged Continue');

  f=await fixture();await f.page.getByRole('button',{name:'Library',exact:true}).click();await f.page.getByRole('button',{name:'Ask & Explore',exact:true}).waitFor();await f.shots('03-library-entry');
  await f.page.getByRole('button',{name:'Ask & Explore',exact:true}).click();await f.page.locator('#ke-ask-card').waitFor();await f.shots('04-explore-initial');assert.equal(await f.page.locator('#ke-chapter-scope').isVisible(),false);assert.equal(await f.page.locator('#ke-idea-scope').isVisible(),false);await f.page.locator('[name=q]').fill('practice breaks');await f.page.getByRole('button',{name:'Find ideas',exact:true}).click();await f.page.getByRole('heading',{name:'Search results for “practice breaks”',exact:true}).waitFor();await f.shots('05-explore-results');await f.page.getByRole('button',{name:'Use this scope in Create',exact:true}).waitFor();await f.shots('11-zero-selection');
  await f.page.locator('#ke-browse summary').click();await f.page.getByText('Browsing 10 of 13 ideas',{exact:true}).waitFor();await f.page.getByRole('button',{name:'Show more',exact:true}).click();await f.page.getByText('Browsing 13 of 13 ideas',{exact:true}).waitFor();
  await f.page.locator('#ke-browse select').first().selectOption('concept');await f.page.getByText('Browsing 7 of 7 ideas',{exact:true}).waitFor();await f.page.locator('#ke-browse select').last().selectOption('Practice');
  await f.page.locator('#ke-browse details').first().locator('summary').click();await f.page.locator('#ke-browse .evidence').first().waitFor();
  const revisedQuestion='practice breaks';
  await f.page.locator('#ke-search-results input[type=checkbox]').first().check();await f.page.getByRole('button',{name:'Use selected ideas in Create',exact:true}).waitFor();await f.shots('12-selected-ideas');await f.page.locator('#ke-search-results input[type=checkbox]').first().uncheck();await f.page.getByRole('button',{name:'Use this scope in Create',exact:true}).waitFor();await f.page.locator('#ke-search-results input[type=checkbox]').first().check();await f.page.getByRole('button',{name:'Use selected ideas in Create',exact:true}).click();await f.page.locator('[name=original_request]').waitFor();assert.equal(await f.page.locator('[name=original_request]').inputValue(),revisedQuestion);assert.equal(f.posts().length,0);
  await f.page.goBack();await f.page.locator('#ke-ask-card').waitFor();assert.equal(await f.page.locator('[name=q]').inputValue(),'practice breaks');assert.equal(await f.page.locator('#ke-browse select').first().inputValue(),'concept');assert.equal(await f.page.locator('#ke-search-results input[type=checkbox]').first().isChecked(),true);
  // Suggestions configure only; all provider actions remain explicit.
  await f.page.locator('.question-suggestions summary').click();
  await f.page.getByRole('button',{name:'Ask about a section',exact:true}).click();
  assert.equal(f.posts().length,0);assert.equal(await f.page.locator('#ke-chapter-scope').isVisible(),true);assert.equal(await f.page.locator('#ke-idea-scope').isVisible(),false);
  await f.page.getByRole('button',{name:'Ask with AI',exact:true}).click();await f.page.getByText('Choose one material first',{exact:true}).waitFor();assert.equal(f.posts().length,0);
  await f.page.locator('#ke-source-scope').selectOption('s1');
  await f.page.locator('.question-suggestions summary').click();await f.page.getByRole('button',{name:'Ask about a section',exact:true}).click();
  await f.page.locator('#ke-chapter-scope').fill('Practice');await f.shots('06-explore-section');
  assert.equal(f.posts().length,0);await f.page.getByRole('button',{name:'Ask with AI',exact:true}).click();
  await f.page.getByRole('heading',{name:'Practice and reflection',exact:true}).waitFor();assert.equal(f.posts().length,1);await f.shots('07-explore-answer');
  assert.deepEqual(f.posts()[0].payload.source_ids,['s1']);assert.ok(JSON.stringify(f.posts()[0].payload).includes('Practice'));
  await f.goHome();await f.page.goBack();await f.page.getByRole('heading',{name:'Practice and reflection',exact:true}).waitFor();assert.equal(f.posts().length,1);assert.equal(await f.page.locator('#ke-chapter-scope').inputValue(),'Practice');
  await f.page.getByRole('button',{name:'Open in Create',exact:true}).click();await f.page.locator('#create-handoff').waitFor();assert.equal(f.posts().length,1);await f.page.close();
  console.log('PASS Library placement, search/browse/filter/pagination/evidence, scoped selections, answer restoration and guarded answer handoff');

  f=await fixture();await f.page.goto('http://ke.test/#/create/ideas?material=s1&source=s1');await f.page.locator('#ke-ask-card').waitFor();assert.ok(f.page.url().includes('/library/explore?'));await f.page.getByRole('button',{name:'Use this scope in Create',exact:true}).click();await f.page.locator('[name=original_request]').waitFor();await f.page.close();console.log('PASS legacy route compatibility');

  f=await fixture(true);await f.shots('09-home-mobile');await f.page.getByLabel('Your request',{exact:true}).fill('practice breaks');await f.page.getByRole('button',{name:'Ask & Explore',exact:true}).focus();await f.page.keyboard.press('Enter');await f.page.locator('#ke-ask-card').waitFor();assert.equal(f.posts().length,0);await f.page.getByRole('button',{name:'Find ideas',exact:true}).click();await f.page.getByRole('heading',{name:'Search results for “practice breaks”',exact:true}).waitFor();await f.shots('10-explore-mobile');assert.equal(await f.page.locator('#ke-chapter-scope').isVisible(),false);const bounds=await f.page.locator('#ke-search-form').boundingBox();assert.ok(bounds.height<550);assert.equal(await f.page.getByRole('button',{name:'Ask with AI',exact:true}).evaluate(e=>e.getBoundingClientRect().height>=44),true);assert.ok(await f.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await f.page.close();
  // A failed explicit action has no retry; a late answer cannot survive typing.
  f=await fixture();await f.page.getByLabel('Your request',{exact:true}).fill('What helps learners reflect?');await f.page.getByRole('button',{name:'Ask & Explore',exact:true}).click();await f.page.locator('#ke-ask-card').waitFor();
  let attempts=0;await f.page.route('**/workshops/generate',async route=>{attempts++;await route.fulfill({status:429,json:{detail:'Daily AI limit reached.'}});});
  await f.page.getByRole('button',{name:'Ask with AI',exact:true}).click();await f.page.getByText('Daily AI limit reached.',{exact:false}).waitFor();assert.equal(attempts,1);
  let release;const pending=new Promise(resolve=>release=resolve);let started;const begin=new Promise(resolve=>started=resolve);
  await f.page.route('**/workshops/generate',async route=>{attempts++;started();await pending;await route.fulfill({json:{output:{title:'Stale answer',content:'Must not return',applied_knowledge:[],design_choices:[]},knowledge_unit_count:0,knowledge_snapshot:[]}});});
  await f.page.getByRole('button',{name:'Ask with AI',exact:true}).click();await begin;await f.page.locator('[name=q]').fill('A changed question');release();await f.page.waitForResponse('**/workshops/generate');await f.page.waitForTimeout(50);assert.equal(await f.page.getByRole('heading',{name:'Stale answer',exact:true}).count(),0);assert.equal(attempts,2);await f.page.close();
  console.log('PASS explicit AI quota failure without retry and stale answer suppression');
  console.log('PASS mobile Home keyboard routing and exploration layout');assert.deepEqual(errors,[]);console.log('5 acceptance groups passed; zero runtime errors and real Gemini calls. Screenshots:',out);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
