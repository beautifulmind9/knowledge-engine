import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createMaterialPreparation} from '../material-preparation.js';

function fixture({limit=450,failAt=0,throwAt=0,summaryFailAt=0,holdAt=0,onProgress=()=>{}}={}){
 const summaries=new Map(['one','two'].map(id=>[id,{readiness:'ready_to_build',completed_parts:0,total_parts:3,has_usable_knowledge:false,operation:'idle',next_action:'build_knowledge'}]));
 const calls=[],opened=[],usage={configured:true,free_tier_confirmed:true,daily_call_limit:limit,calls_today:0,daily_limit_reached:limit===0};let release,entered,posts=0,active=0,peak=0;
 const held=new Promise(r=>release=r),started=new Promise(r=>entered=r);
 const api=async(path,options)=>{
  calls.push({path,options});if(path==='/usage')return {...usage};const id=path.split('/')[2],summary=summaries.get(id);
  if(!options){if(summaryFailAt&&posts===summaryFailAt)throw Error('Status unavailable');return {...summary};}
  posts++;active++;peak=Math.max(peak,active);
  try{
   if(posts===holdAt){entered();await held;}
   if(posts===throwAt)throw Error('Uncertain transport');
   if(posts===failAt){summary.attention_category='build_stopped';return {processed_this_run:0,stopped_reason:'Private diagnostic'};}
   usage.calls_today++;usage.daily_limit_reached=usage.calls_today>=usage.daily_call_limit;
   summary.completed_parts++;summary.has_usable_knowledge=true;summary.readiness=summary.completed_parts===3?'ready':'partly_ready';summary.next_action=summary.readiness==='ready'?'use_knowledge':'continue_building';
   return {processed_this_run:1};
  }finally{active--;}
 };
 const run=createMaterialPreparation({sourceIds:['one','two'],api,onSource:async id=>opened.push(id),onProgress});
 return {run,summaries,usage,calls,opened,release,started,peak:()=>peak,posts:()=>calls.filter(c=>c.options)};
}
test('Add authorization prepares multiple materials sequentially with independent one-part requests',async()=>{
 const f=fixture();assert.equal(f.calls.length,0);const result=await f.run.run();
 assert.equal(result.status,'completed');assert.deepEqual(f.opened,['one','two']);assert.equal(f.posts().length,6);assert.equal(f.peak(),1);
 assert.ok(f.posts().every(c=>c.path.endsWith('/interpret?max_chunks=1')));
 assert.deepEqual(f.posts().map(c=>c.path.split('/')[2]),['one','one','one','two','two','two']);
 await f.run.run();assert.equal(f.posts().length,6);
});
test('shared allowance bounds the entire selected set and cannot grow mid-run',async()=>{
 const f=fixture({limit:2,holdAt:1}),pending=f.run.run();await f.started;
 f.usage.daily_call_limit=450;f.release();const result=await pending;
 assert.equal(f.posts().length,2);assert.equal(f.summaries.get('one').completed_parts,2);assert.equal(f.summaries.get('two').completed_parts,0);assert.equal(result.status,'incomplete');
});
test('allowance exhaustion pauses preparation without losing saved sibling state',async()=>{
 const f=fixture({limit:4});const result=await f.run.run();
 assert.equal(result.status,'daily_allowance');assert.equal(f.posts().length,4);assert.equal(result.outcomes.get('one').category,'completed');assert.equal(result.outcomes.get('two').category,'daily_allowance');
});
for(const [name,options,category] of [['backend failure',{failAt:2},'failed'],['transport uncertainty',{throwAt:2},'uncertain'],['status failure',{summaryFailAt:1},'status_unavailable']]){
 test(`${name} stops immediately without retries or another material dispatch`,async()=>{
  const f=fixture(options);const result=await f.run.run();assert.equal(result.status,category);assert.deepEqual(f.opened,['one']);assert.equal(f.posts().length,name==='status failure'?1:2);assert.equal(f.summaries.get('one').completed_parts,1);assert.equal(f.summaries.get('two').completed_parts,0);
 });
}
test('Stop allows in-flight success and stops before another part or sibling',async()=>{
 const f=fixture({holdAt:2});const pending=f.run.run();await f.started;f.run.stop();assert.equal(f.posts().length,2);f.release();const result=await pending;
 assert.equal(result.status,'stopped');assert.equal(f.summaries.get('one').completed_parts,2);assert.equal(f.posts().length,2);
});
test('navigation stops subsequent dispatch; creating a new coordinator never resumes',async()=>{
 const f=fixture({holdAt:2});const pending=f.run.run();await f.started;f.run.stop('navigation');f.release();const result=await pending;assert.equal(result.status,'left');assert.equal(f.posts().length,2);
 const refreshed=fixture();await Promise.resolve();assert.equal(refreshed.calls.length,0);
});
test('zero allowance dispatches nothing',async()=>{
 const f=fixture({limit:0});const result=await f.run.run();assert.equal(result.status,'daily_allowance');assert.equal(f.posts().length,0);
});
test('progress exposes newly usable server knowledge before the material is complete',async()=>{
 let usableBeforeReady=false;const f=fixture({onProgress:s=>{const o=s.outcomes.get('one');if(o?.summary?.has_usable_knowledge&&o.summary.readiness==='partly_ready')usableBeforeReady=true;}});
 await f.run.run();assert.equal(usableBeforeReady,true);
});
test('navigation while opening the next material cannot dispatch that material',async()=>{
 let posts=0,run;const usage={configured:true,free_tier_confirmed:true,daily_call_limit:450,calls_today:0};
 run=createMaterialPreparation({sourceIds:['one','two'],api:async(_path,options)=>options?(posts++,{processed_this_run:1}):_path==='/usage'?usage:{readiness:'ready_to_build',completed_parts:0,total_parts:1,operation:'idle',next_action:'build_knowledge'},onSource:async id=>{if(id==='two')run.stop('navigation');}});
 const result=await run.run();assert.equal(posts,1);assert.equal(result.status,'left');
});
test('unavailable initial allowance records an in-tab blocked outcome without dispatch',async()=>{
 let posts=0;const run=createMaterialPreparation({sourceIds:['one'],api:async(_path,options)=>{if(options)posts++;throw Error('Unavailable');}});
 const result=await run.run();assert.equal(posts,0);assert.equal(result.outcomes.get('one').category,'allowance_unavailable');
});
