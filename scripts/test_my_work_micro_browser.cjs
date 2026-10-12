// Synthetic review for saved evidence, shared AI usage, and manual/AI revision labels.
// All APIs are fixture responses; this script never contacts a provider.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const screenshots=process.env.KNOWLEDGE_ENGINE_SCREENSHOTS||path.join(root,'outputs/prebeta-micro-review');
fs.mkdirSync(screenshots,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  async function page(mobile=false,hash='#/my-work/o1'){
   const p=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000},isMobile:mobile,hasTouch:mobile});const calls=[];let versionNo=1;
   await p.route('http://ke.test/**',async route=>{
    const u=new URL(route.request().url()),pathName=u.pathname,method=route.request().method();
    if(pathName==='/'||pathName.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',pathName==='/'?'index.html':pathName.slice(8))),contentType:pathName.endsWith('.js')?'text/javascript':pathName.endsWith('.css')?'text/css':'text/html'});
    const body=method==='POST'?route.request().postDataJSON():null;if(body)calls.push({path:pathName,body});
    if(/^\/outputs\/[^/]+$/.test(pathName))return route.fulfill({json:{id:pathName.split('/').at(-1),title:'Practice session outline',content:'Start with a short exercise.',output_type:'workshop_plan',version:Number(pathName.split('/').at(-1).slice(1)),created_at:'2026-10-12T10:00:00Z',provider:'manual',applied_knowledge:[{asset_id:'asset-internal-17',usage_note:'Used to shape the opening exercise.'}],knowledge_snapshot:[{canonical_asset:{id:'asset-internal-17',title:'Practice breaks'},evidence_trail:[{source_id:'source-internal-42',chunk_id:'chunk-internal-8',chapter_or_section:'Facilitator guide · Section 3',evidence:'A pause after practice gives participants time to reflect.'}]}],design_choices:['Keep the opening short.']}});
    if(pathName==='/sources')return route.fulfill({json:{items:[{id:'source-internal-42',title:'Facilitator notes'}]}});
    if(pathName.endsWith('/quality'))return route.fulfill({json:{validation_status:'needs_review',issues:[],note:'Review before use.'}});
    if(pathName.endsWith('/history'))return route.fulfill({json:{items:Array.from({length:versionNo},(_,i)=>({id:`o${i+1}`,version:i+1}))}});
    if(pathName.endsWith('/revise'))return route.fulfill({json:{id:`o${++versionNo}`,version:versionNo}});
    if(pathName==='/usage')return route.fulfill({json:{configured:true,free_tier_confirmed:true,calls_today:7,daily_call_limit:20,paused:false,daily_limit_reached:false}});
    if(pathName==='/data/integrity')return route.fulfill({json:{ok:true,issues:[]}});
    return route.fulfill({json:{items:[],count:0}});
   });
   await p.goto('http://ke.test/'+hash);return {page:p,calls};
  }
  let f=await page();await f.page.getByText('Ideas and evidence used',{exact:true}).click();await f.page.getByText('Source & evidence',{exact:true}).click();
  const text=await f.page.locator('main').innerText();assert.match(text,/Facilitator notes/);assert.match(text,/Facilitator guide · Section 3/);assert.match(text,/A pause after practice gives participants time to reflect/);assert.doesNotMatch(text,/source-internal-42|chunk-internal-8|asset-internal-17/);
  await f.page.getByText('Revise this work',{exact:true}).click();const manual=f.page.getByRole('button',{name:'Save manual edits',exact:true});assert.equal(await manual.isVisible(),true);assert.match(await f.page.locator('main').innerText(),/No AI used/);await f.page.screenshot({path:path.join(screenshots,'04-manual-revision.png'),fullPage:true});
  await f.page.locator('[name=instruction]').fill('Save a concise manual edit.');await manual.click();await f.page.waitForURL('**/#/my-work/o2');assert.equal(f.calls.filter(x=>x.path.endsWith('/revise')).length,1);assert.ok('content' in f.calls[0].body);assert.equal(f.calls.filter(x=>x.path==='/workshops/generate').length,0);await f.page.getByRole('button',{name:'Open version 1',exact:true}).waitFor();await f.page.getByRole('button',{name:'Open version 2',exact:true}).waitFor();await f.page.getByRole('button',{name:'Compare v2 → v1',exact:true}).waitFor();assert.match(await f.page.locator('main').innerText(),/VERSION 2/);assert.equal(await f.page.getByRole('button',{name:/Compare v1 → v1/}).count(),0);await f.page.screenshot({path:path.join(screenshots,'04-manual-revision.png'),fullPage:true});
  await f.page.getByText('Revise this work',{exact:true}).click();await f.page.locator('[name=manual]').uncheck();const ai=f.page.getByRole('button',{name:'Revise with AI',exact:true});assert.match(await f.page.locator('main').innerText(),/one explicit AI revision request/);await f.page.locator('[name=instruction]').fill('Ask AI for a concise revision.');await ai.click();await f.page.waitForURL('**/#/my-work/o3');const revisions=f.calls.filter(x=>x.path.endsWith('/revise'));assert.equal(revisions.length,2);assert.deepEqual(Object.keys(revisions[1].body),['instruction']);assert.equal(f.calls.filter(x=>x.path==='/workshops/generate').length,0);for(const name of ['Open version 1','Open version 2','Open version 3'])await f.page.getByRole('button',{name,exact:true}).waitFor();await f.page.getByRole('button',{name:'Compare v3 → v1',exact:true}).waitFor();await f.page.getByRole('button',{name:'Compare v3 → v2',exact:true}).waitFor();assert.match(await f.page.locator('main').innerText(),/VERSION 3/);assert.equal(await f.page.getByRole('button',{name:/Compare v1 → v1|Compare v3 → v3/}).count(),0);await f.page.screenshot({path:path.join(screenshots,'05-ai-revision.png'),fullPage:true});await f.page.getByRole('button',{name:'Open version 1',exact:true}).click();await f.page.waitForURL('**/#/my-work/o1');await f.page.locator('article').getByText('Start with a short exercise.').waitFor();assert.match(await f.page.locator('main').innerText(),/VERSION 1/);await f.page.close();
  f=await page(false,'#/settings');const settings=await f.page.locator('main').innerText();assert.match(settings,/Shared beta allowance/);assert.match(settings,/AI actions used today: 7 of 20/);assert.match(settings,/AI actions remaining today: 13/);assert.match(settings,/shared across the workspace/);assert.match(settings,/do not use AI actions/);assert.match(settings,/configured to stay within the approved \$0 beta policy/i);assert.doesNotMatch(settings,/Gemini key|free-project confirmation|billing is verified by its owner/i);await f.page.screenshot({path:path.join(screenshots,'03-settings-shared-usage.png'),fullPage:true});await f.page.close();
  assert.deepEqual(f?.calls||[],[]);console.log('PASS saved evidence is human-readable; shared allowance and explicit revision modes verified. Screenshots:',screenshots);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
