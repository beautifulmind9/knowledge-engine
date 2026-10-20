// Synthetic browser acceptance only: no server or model calls.
const {chromium}=require(process.env.KNOWLEDGE_ENGINE_PLAYWRIGHT||'playwright');
const fs=require('fs'),assert=require('assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..');
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.KNOWLEDGE_ENGINE_CHROME?{executablePath:process.env.KNOWLEDGE_ENGINE_CHROME}:{})});const errors=[];
for(const mobile of [false,true]){const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1280,height:1000}});page.on('pageerror',e=>errors.push(e.message));let failed=true;const writes=[];
const sources=[{id:'one',title:'First book',library_id:'a'},{id:'two',title:'Second book',library_id:'a'}];
await page.route('http://ke.test/**',async route=>{const req=route.request(),url=new URL(req.url()),p=url.pathname;let data;
if(p==='/'||p.startsWith('/static/'))return route.fulfill({body:fs.readFileSync(path.join(root,'apps/web',p==='/'?'index.html':p.slice(8))),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});
if(p==='/libraries')data={items:[{id:'a',name:'Reading'},{id:'b',name:'Reference'}]};
else if(p==='/sources')data={items:sources.filter(s=>!url.searchParams.get('library_id')||s.library_id===url.searchParams.get('library_id'))};
else if(p==='/sources/summaries')data=[];
else if(req.method()==='PUT'){writes.push(p);if(p.includes('/two/')&&failed){failed=false;return route.fulfill({status:500,json:{detail:'Synthetic failed save'}});}sources.find(s=>p.includes('/'+s.id+'/')).library_id=req.postDataJSON().library_id;data={changed:true};}
else throw Error('Unexpected '+p);return route.fulfill({json:data});});
await page.goto('http://ke.test/#/library');await page.getByLabel('Filter by library').selectOption('a');
await page.getByRole('checkbox',{name:'Select First book',exact:true}).check();await page.getByRole('checkbox',{name:'Select Second book',exact:true}).check();await page.getByRole('button',{name:'Move selected',exact:true}).click();await page.getByLabel('Destination library').selectOption('b');await page.getByText('First book · Reading → Reference',{exact:true}).waitFor();assert.equal(writes.length,0);
await page.getByRole('button',{name:'Confirm move',exact:true}).click();await page.getByText('1 of 2 materials moved to Reference.',{exact:true}).waitFor();await page.getByRole('checkbox',{name:'Select Second book',exact:true}).waitFor();assert.equal(await page.getByRole('checkbox',{name:'Select First book',exact:true}).count(),0);assert.equal(await page.getByRole('checkbox',{name:'Select Second book',exact:true}).isChecked(),true);
await page.getByRole('button',{name:'Move selected',exact:true}).click();await page.getByLabel('Destination library').selectOption('b');await page.getByRole('button',{name:'Confirm move',exact:true}).click();await page.getByText('1 of 1 materials moved to Reference.',{exact:true}).waitFor();await page.getByRole('button',{name:'View destination library'}).click();await page.getByRole('checkbox',{name:'Select First book',exact:true}).waitFor();await page.getByRole('checkbox',{name:'Select Second book',exact:true}).waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.equal(writes.length,3);await page.screenshot({path:'/private/tmp/ke-bulk-'+(mobile?'mobile':'desktop')+'.png',fullPage:true});await page.close();}
assert.deepEqual(errors,[]);await browser.close();console.log('Desktop and mobile: preview, partial failure, retained selection, retry, refreshed old/destination listings, no overflow or runtime errors passed.');})().catch(e=>{console.error(e);process.exit(1);});
