import {test} from 'node:test';
import assert from 'node:assert/strict';
import {availableAIAllowance, buildQuantity, createKnowledgeBuild} from '../knowledge-build.js';

const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
function fixture({remaining=6,allowance=450,existing=0,failureAt=0,throwAt=0,holdAt=0,summaryFails=false,onProgress=()=>{}}={}){
 const usage={configured:true,free_tier_confirmed:true,daily_call_limit:450,calls_today:450-allowance,paused:false};
 const calls=[],progress=[],held=deferred(),entered=deferred();let inFlight=0,peak=0,stored=existing,active=true;
 const api=async(path,options)=>{
  calls.push({path,options});
  if(!options){if(summaryFails)throw Error('Synthetic status failure');return {readiness:stored===existing+remaining?'ready':stored?'partly_ready':'ready_to_build',completed_parts:stored,total_parts:existing+remaining,has_usable_knowledge:stored>0,attention_category:failureAt?'build_stopped':null};}
  const number=calls.filter(call=>call.options).length;
  inFlight++;peak=Math.max(peak,inFlight);
  try{
   if(number===holdAt){entered.resolve();await held.promise;}
   await Promise.resolve();
   if(number===throwAt)throw Error('Synthetic uncertain transport');
   if(number===failureAt)return {processed_this_run:0,stopped_reason:'Synthetic provider/validation/quota stop'};
   usage.calls_today++;stored++;return {processed_this_run:1};
  }finally{inFlight--;}
 };
 const run=createKnowledgeBuild({sourceId:'source / private',remainingParts:remaining,usage,api,isActive:()=>active,onProgress:snapshot=>{progress.push(snapshot);onProgress(snapshot);}});
 return {run,usage,calls,progress,held,entered,leave:()=>active=false,peak:()=>peak,posts:()=>calls.filter(call=>call.options)};
}

test('six authorized parts use exactly six sequential one-part requests and refreshed server truth',async()=>{
 const f=fixture();const result=await f.run.run();
 assert.equal(result.authorized,6);assert.equal(result.completed,6);assert.equal(result.status,'completed');assert.equal(f.peak(),1);
 assert.equal(f.posts().length,6);assert.ok(f.posts().every(call=>call.path==='/sources/source%20%2F%20private/interpret?max_chunks=1'&&call.options.method==='POST'));
 assert.deepEqual([...new Set(f.progress.map(step=>step.completed))],[0,1,2,3,4,5,6]);
 assert.equal(f.calls.at(-1).path,'/sources/source%20%2F%20private/summary');assert.equal(result.summary.readiness,'ready');
 await f.run.run();assert.equal(f.posts().length,6);
});
test('allowance snapshot bounds authorization without an arbitrary part ceiling',async()=>{
 const f=fixture({remaining:63,allowance:17});const result=await f.run.run();
 assert.equal(result.authorized,17);assert.equal(f.posts().length,17);assert.equal(result.summary.readiness,'partly_ready');
 assert.equal(buildQuantity(63,{...f.usage,calls_today:0}),63);
});
test('increasing allowance during the run cannot enlarge its authorization',async()=>{
 const f=fixture({remaining:63,allowance:2,holdAt:1});const pending=f.run.run();await f.entered.promise;
 f.usage.calls_today=0;f.held.resolve();const result=await pending;
 assert.equal(result.authorized,2);assert.equal(f.posts().length,2);
});
test('a fresh allowance check cannot exceed the quantity already shown to the user',async()=>{
 let posts=0;const usage={configured:true,free_tier_confirmed:true,daily_call_limit:450,calls_today:0};
 const run=createKnowledgeBuild({sourceId:'s1',remainingParts:63,usage,authorizationLimit:17,api:async(_path,options)=>options?(posts++,{processed_this_run:1}):{readiness:'partly_ready'}});
 const result=await run.run();assert.equal(result.authorized,17);assert.equal(posts,17);
});
test('server provider, validation or quota stop preserves confirmed parts and dispatches no later part',async()=>{
 const f=fixture({existing:12,failureAt:3});const result=await f.run.run();
 assert.equal(result.status,'failed');assert.equal(result.completed,2);assert.equal(f.posts().length,3);assert.equal(result.summary.completed_parts,14);assert.equal(result.summary.has_usable_knowledge,true);
 assert.equal(result.summary.attention_category,'build_stopped');
});
test('uncertain transport is not retried and confirmed prior progress remains known',async()=>{
 const f=fixture({throwAt:3});const result=await f.run.run();
 assert.equal(result.status,'uncertain');assert.equal(result.completed,2);assert.equal(f.posts().length,3);assert.equal(result.summary.completed_parts,2);
});
test('Stop lets the current request finish normally before stopping',async()=>{
 const f=fixture({holdAt:2});const pending=f.run.run();await f.entered.promise;
 f.run.stop();assert.equal(f.run.snapshot().inFlight,true);assert.equal(f.run.snapshot().completed,1);assert.equal(f.posts().length,2);
 f.held.resolve();const result=await pending;
 assert.equal(result.status,'stopped');assert.equal(result.completed,2);assert.equal(result.notStarted,4);assert.equal(f.posts().length,2);assert.equal(result.summary.completed_parts,2);
});
test('Stop before dispatch, including between confirmed parts, starts no further request',async()=>{
 const before=fixture();before.run.stop();assert.equal(before.run.snapshot().status,'stopped');const zero=await before.run.run();assert.equal(zero.status,'stopped');assert.equal(before.posts().length,0);
 let run;const f=fixture({onProgress:step=>{if(step.completed===1&&!step.inFlight)run.stop();}});run=f.run;
 const result=await run.run();assert.equal(result.status,'stopped');assert.equal(f.posts().length,1);
});
test('navigation during an uncertain operation dispatches no subsequent request or automatic retry',async()=>{
 const f=fixture({holdAt:2});const pending=f.run.run();await f.entered.promise;
 f.leave();f.held.reject(Error('Synthetic navigation disconnect'));const result=await pending;
 assert.equal(result.status,'left');assert.equal(result.completed,1);assert.equal(f.posts().length,2);assert.equal(f.calls.filter(call=>!call.options).length,1);
});
test('navigation after a confirmed response keeps its result but never continues',async()=>{
 const f=fixture({holdAt:2});const pending=f.run.run();await f.entered.promise;f.leave();f.held.resolve();
 const result=await pending;assert.equal(result.completed,2);assert.equal(result.status,'left');assert.equal(f.posts().length,2);
});
test('new page initialization never automatically starts or resumes a build',async()=>{
 const f=fixture();await Promise.resolve();assert.equal(f.calls.length,0);assert.equal(f.run.snapshot().status,'idle');
 const refreshed=fixture();await Promise.resolve();assert.equal(refreshed.calls.length,0);
});
test('depleted, paused or unverifiable allowance cannot dispatch',async()=>{
 const f=fixture({allowance:0});const result=await f.run.run();assert.equal(result.status,'unavailable');assert.equal(f.calls.length,0);
 for(const usage of [null,{configured:true,free_tier_confirmed:true,paused:true,daily_call_limit:450,calls_today:0},{configured:true,free_tier_confirmed:true,daily_call_limit:'invalid',calls_today:0}])assert.equal(availableAIAllowance(usage),0);
});
test('summary failure preserves confirmed results without inventing readiness',async()=>{
 const f=fixture({remaining:2,summaryFails:true});const result=await f.run.run();
 assert.equal(result.status,'status_unavailable');assert.equal(result.completed,1);assert.equal(result.summary,null);assert.equal(result.summaryUnavailable,true);assert.equal(f.posts().length,1);
});
test('unconfirmed or impossible success counts never cause another dispatch',async()=>{
 for(const processed of [0,2,undefined]){
  let calls=0;const usage={configured:true,free_tier_confirmed:true,daily_call_limit:450,calls_today:0};
  const run=createKnowledgeBuild({sourceId:'s1',remainingParts:6,usage,api:async(_path,options)=>options?(calls++,{processed_this_run:processed}):{readiness:'unknown'}});
  const result=await run.run();assert.equal(result.status,'uncertain');assert.equal(result.completed,0);assert.equal(calls,1);
 }
});
