import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createMaterialPreparation} from '../material-preparation.js';

function fixture({ids=['one','two'],parts=3,limit=450,failures={},throwAt=null,summaryFailAt=0,holdAt=0,onProgress=()=>{}}={}){
 const summaries=new Map(ids.map(id=>[id,{readiness:'ready_to_build',completed_parts:0,total_parts:parts,has_usable_knowledge:false,operation:'idle',next_action:'build_knowledge'}]));
 const calls=[],opened=[],attempts=new Map(),usage={configured:true,free_tier_confirmed:true,daily_call_limit:limit,calls_today:0,daily_limit_reached:limit===0};let release,entered,posts=0,active=0,peak=0;
 const held=new Promise(r=>release=r),started=new Promise(r=>entered=r);
 const api=async(path,options)=>{
  calls.push({path,options});if(path==='/usage')return {...usage};const id=path.split('/')[2],summary=summaries.get(id);
  if(!options){if(summaryFailAt&&posts===summaryFailAt)throw Error('Status unavailable');return {...summary};}
  posts++;usage.calls_today++;active++;peak=Math.max(peak,active);
  try{
   if(posts===holdAt){entered();await held;}
   const attempt=(attempts.get(id)||0)+1;attempts.set(id,attempt);
   if(throwAt===posts)throw Error('Uncertain transport');
   if((failures[id]||[]).includes(attempt)){
    summary.attention_category='build_stopped';summary.readiness=summary.completed_parts?'partly_ready':'ready_to_build';summary.next_action=summary.completed_parts?'continue_building':'build_knowledge';
    const interruptionCategory=failures.category||'provider_unavailable';
    // Model the backend's confirmed-503 result: one logical /interpret request
    // may consume two allowance attempts before the frontend receives it.
    if(interruptionCategory==='provider_unavailable')usage.calls_today++;
    return {processed_this_run:0,stopped_reason:'Private diagnostic',interruption_category:interruptionCategory};
   }
   summary.completed_parts++;summary.has_usable_knowledge=summary.completed_parts>0;summary.readiness=summary.completed_parts===parts?'ready':'partly_ready';summary.next_action=summary.readiness==='ready'?'use_knowledge':'continue_building';summary.attention_category=null;
   usage.daily_limit_reached=usage.calls_today>=usage.daily_call_limit;
   return {processed_this_run:1};
  }finally{active--;}
 };
 const run=createMaterialPreparation({sourceIds:ids,api,onSource:async id=>opened.push(id),onProgress});
 return {run,summaries,usage,calls,opened,release,started,peak:()=>peak,posts:()=>calls.filter(c=>c.options)};
}
test('one Add authorization sequentially prepares all six selected materials',async()=>{
 const ids=['one','two','three','four','five','six'],f=fixture({ids,parts:2});const result=await f.run.run();
 assert.equal(result.status,'completed');assert.deepEqual(f.opened,ids);assert.equal(f.posts().length,12);assert.equal(f.peak(),1);
 assert.ok(f.posts().every(c=>c.path.endsWith('/interpret?max_chunks=1')));
 assert.deepEqual([...new Set(f.posts().map(c=>c.path.split('/')[2]))],ids);
});
test('provider outage on first material stops a three-material batch without failing queued siblings',async()=>{
 const ids=['one','two','three'],f=fixture({ids,parts:2,failures:{one:[1],category:'provider_unavailable'}});const result=await f.run.run();
 assert.equal(result.status,'provider_unavailable');assert.equal(f.posts().length,1);
 assert.deepEqual(f.opened,['one']);assert.equal(f.summaries.get('one').completed_parts,0);
 assert.equal(f.summaries.get('two').readiness,'ready_to_build');assert.equal(f.summaries.get('three').readiness,'ready_to_build');
 assert.equal(result.outcomes.get('one').category,'provider_unavailable');
 assert.equal(result.outcomes.get('two').category,'not_started');assert.equal(result.outcomes.get('three').category,'not_started');
 assert.equal(f.usage.calls_today,2,'the bounded 503 retry consumes two real allowance attempts');
});
test('Continue incomplete materials is a fresh explicit attempt for only the incomplete material',async()=>{
 const summaries=new Map(['one','two','three'].map(id=>[id,{readiness:'ready_to_build',completed_parts:0,total_parts:1,has_usable_knowledge:false,operation:'idle',next_action:'build_knowledge'}]));let calls=0,fail=true;
 const api=async(path,options)=>{if(path==='/usage')return {configured:true,free_tier_confirmed:true,daily_call_limit:450,calls_today:calls};const id=path.split('/')[2];if(!options)return {...summaries.get(id)};calls++;if(id==='two'&&fail)return {processed_this_run:0,stopped_reason:'stopped',interruption_category:'provider_unavailable'};const s=summaries.get(id);s.completed_parts=1;s.readiness='ready';s.next_action='use_knowledge';return {processed_this_run:1};};
 const first=await createMaterialPreparation({sourceIds:['one','two','three'],api}).run();assert.equal(first.status,'provider_unavailable');assert.equal(calls,2);assert.equal(first.outcomes.get('three').category,'not_started');
 fail=false;const continued=await createMaterialPreparation({sourceIds:['two'],api}).run();assert.equal(continued.status,'completed');assert.equal(calls,3);assert.equal(summaries.get('one').completed_parts,1);assert.equal(summaries.get('three').completed_parts,0);assert.equal(summaries.get('two').readiness,'ready');
});
test('provider outage preserves prior completed sibling and leaves later siblings unattempted',async()=>{
 const ids=['one','two','three'],f=fixture({ids,parts:1,failures:{two:[1],category:'provider_unavailable'}});const result=await f.run.run();
 assert.equal(result.status,'provider_unavailable');assert.equal(result.outcomes.get('one').category,'completed');assert.equal(result.outcomes.get('two').category,'provider_unavailable');assert.equal(result.outcomes.get('three').category,'not_started');
 assert.equal(f.summaries.get('one').readiness,'ready');assert.equal(f.summaries.get('one').completed_parts,1);assert.equal(f.summaries.get('two').completed_parts,0);assert.equal(f.summaries.get('three').completed_parts,0);
 assert.equal(f.posts().filter(c=>c.path.includes('/one/')).length,1);assert.equal(f.posts().filter(c=>c.path.includes('/two/')).length,1);assert.equal(f.posts().filter(c=>c.path.includes('/three/')).length,0);
});
test('shared allowance exhaustion stops dispatching new material while preserving earlier successes',async()=>{
 const ids=['one','two','three','four','five','six'],f=fixture({ids,parts:2,limit:5});const result=await f.run.run();
 assert.equal(result.status,'daily_allowance');assert.equal(f.posts().length,5);assert.equal(f.summaries.get('one').readiness,'ready');assert.equal(f.summaries.get('two').readiness,'ready');assert.equal(f.summaries.get('three').completed_parts,1);
 assert.equal(result.outcomes.get('three').category,'daily_allowance');
});
test('material-specific strict validation failure does not stop sibling evaluation',async()=>{
 const f=fixture({failures:{one:[1],category:'failed'}}),result=await f.run.run();assert.equal(result.status,'incomplete');assert.equal(result.outcomes.get('one').category,'failed');assert.equal(result.outcomes.get('two').category,'completed');assert.equal(f.posts().length,4);assert.deepEqual(f.opened,['one','two']);
});
test('a single material retains its exact safe interruption category for source detail',async()=>{
 const f=fixture({ids:['one'],failures:{one:[2],category:'provider_unavailable'}}),result=await f.run.run();assert.equal(result.status,'provider_unavailable');assert.equal(result.outcomes.get('one').category,'provider_unavailable');assert.equal(f.posts().length,2);
});
test('a confirmed timeout pauses only that material and later siblings remain ready',async()=>{
 const ids=['one','two','three'],f=fixture({ids,parts:2,failures:{two:[2],category:'request_timed_out'}});const result=await f.run.run();
 assert.equal(result.status,'incomplete');assert.equal(result.outcomes.get('two').category,'preparation_timeout');
 assert.equal(f.summaries.get('one').readiness,'ready');assert.equal(f.summaries.get('two').completed_parts,1);assert.equal(f.summaries.get('three').readiness,'ready');
 assert.equal(f.posts().filter(c=>c.path.includes('/two/')).length,2);assert.equal(f.posts().filter(c=>c.path.includes('/one/')).length,2);assert.equal(f.posts().filter(c=>c.path.includes('/three/')).length,2);
});
test('transport uncertainty never retries the material and sibling dispatch is independent',async()=>{
 const f=fixture({throwAt:2}),result=await f.run.run();assert.equal(result.status,'incomplete');assert.equal(result.outcomes.get('one').category,'uncertain');assert.equal(f.summaries.get('two').readiness,'ready');assert.equal(f.posts().filter(c=>c.path.includes('/one/')).length,2);assert.equal(f.posts().filter(c=>c.path.includes('/two/')).length,3);
});
test('Stop allows the current request to finish and prevents later siblings',async()=>{
 const f=fixture({holdAt:2}),pending=f.run.run();await f.started;f.run.stop();f.release();const result=await pending;assert.equal(result.status,'stopped');assert.equal(f.summaries.get('one').completed_parts,2);assert.equal(f.summaries.get('two').completed_parts,0);assert.equal(f.posts().length,2);
});
test('navigation stops subsequent dispatch; a new page does not automatically resume',async()=>{
 const f=fixture({holdAt:2}),pending=f.run.run();await f.started;f.run.stop('navigation');f.release();const result=await pending;assert.equal(result.status,'left');assert.equal(f.posts().length,2);
});
test('zero allowance dispatches no material request',async()=>{const f=fixture({limit:0});const result=await f.run.run();assert.equal(result.status,'daily_allowance');assert.equal(f.posts().length,0);});
test('progress exposes newly usable knowledge before every selected material is complete',async()=>{
 let usableWhilePreparing=false;const f=fixture({onProgress:s=>{usableWhilePreparing ||= [...s.outcomes.values()].some(o=>o.summary?.has_usable_knowledge&&o.summary.readiness==='partly_ready');}});await f.run.run();assert.equal(usableWhilePreparing,true);
});
test('status refresh failure is isolated to its material and later material still completes',async()=>{
 const f=fixture({summaryFailAt:1}),result=await f.run.run();assert.equal(result.status,'incomplete');assert.equal(result.outcomes.get('one').category,'status_unavailable');assert.equal(f.summaries.get('two').readiness,'ready');assert.equal(f.posts().length,4);
});
test('callback failure remains a batch-wide stop',async()=>{const f=fixture({onProgress(){throw Error('synthetic render failure');}});const result=await f.run.run();assert.equal(result.status,'status_unavailable');assert.equal(f.posts().length,0);});
