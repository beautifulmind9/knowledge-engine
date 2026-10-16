import {availableAIAllowance, createKnowledgeBuild} from './knowledge-build.js';

// One foreground Add/Continue authorization. Nothing here survives a refresh.
export function createMaterialPreparation({sourceIds, api, onSource=async()=>{}, onProgress=()=>{}}) {
  const ids=[...new Set(sourceIds)], outcomes=new Map();
  const perfNow=()=>{try{return globalThis.performance?.now?.()??Date.now();}catch{return Date.now();}};
  const runStarted=perfNow(), firstUsableAt=new Map(), readyAt=new Map();
  const perf=(event,fields={})=>{try{console.info('KE_PERF',{event,...fields});}catch{}};
  let current=null, stopped=false, left=false, callbackFailure=false, promise, status='idle', currentId=null,totalWork=0,initialWork=0;
  const snapshot=()=>({status,currentId,outcomes:new Map(outcomes),sourceIds:ids.slice(),totalWork,
    completedWork:initialWork+[...outcomes.values()].reduce((sum,outcome)=>sum+Number(outcome.completed||0),0)});
  const emit=()=>{try{onProgress(snapshot());return true;}catch{callbackFailure=true;stopped=true;status='status_unavailable';current?.stop();return false;}};
  async function execute(){
    status='running';
    perf('preparation_batch_start',{selected_count:ids.length,source_ids:ids});
    let usage;
    try {usage=await api('/usage');} catch {
      status='allowance_unavailable';for(const id of ids)outcomes.set(id,{category:status,summary:null});
      emit();return snapshot();
    }
    const plans=[];
    for(const id of ids){
      if(stopped||left)break;
      try{
        const summary=await api(`/sources/${encodeURIComponent(id)}/summary`);
        const remaining=Number.isInteger(summary.total_parts)&&Number.isInteger(summary.completed_parts)?Math.max(0,summary.total_parts-summary.completed_parts):0;
        if(summary.completed_parts>0)perf('preparation_continuation',{source_id:id,completed_parts:summary.completed_parts});
        if(Number.isInteger(summary.total_parts)&&Number.isInteger(summary.completed_parts)){totalWork+=summary.total_parts;initialWork+=summary.completed_parts;}
      outcomes.set(id,{category:'not_started',summary});
        if(remaining&&summary.operation!=='build_unconfirmed'&&['build_knowledge','continue_building'].includes(summary.next_action))plans.push({id,remaining});
      }catch{outcomes.set(id,{category:'status_unavailable',summary:null});}
    }
    let budget=availableAIAllowance(usage), started=0;
    const authorized=Math.min(budget,plans.reduce((sum,p)=>sum+p.remaining,0));
    budget=authorized;
    for(const [index,plan] of plans.entries()){
      if(stopped||left||!budget)break;
      currentId=plan.id;
      const sourceStarted=perfNow();
      perf('preparation_queue_dispatch',{source_id:plan.id,queue_position:index+1,selected_count:ids.length,
        wait_behind_earlier_sources_ms:Math.round((sourceStarted-runStarted)*100)/100});
      try{await onSource(plan.id,index,plans.length);}catch{status='status_unavailable';break;}
      if(stopped||left)break;
      current=createKnowledgeBuild({sourceId:plan.id,remainingParts:plan.remaining,
        usage:{...usage,calls_today:Number(usage.calls_today)+started},authorizationLimit:budget,api,isActive:()=>!left,
        onProgress:progress=>{
          outcomes.set(plan.id,{category:'running',completed:progress.completed||0,...progress});
          const usable=progress.summary?.has_usable_knowledge;
          if(usable&&!firstUsableAt.has(plan.id)){firstUsableAt.set(plan.id,perfNow());perf('material_first_usable',{source_id:plan.id,queue_position:index+1,elapsed_ms:Math.round((perfNow()-runStarted)*100)/100});}
          if(progress.summary?.readiness==='ready'&&!readyAt.has(plan.id)){readyAt.set(plan.id,perfNow());perf('material_ready',{source_id:plan.id,queue_position:index+1,elapsed_ms:Math.round((perfNow()-runStarted)*100)/100,source_preparation_ms:Math.round((perfNow()-sourceStarted)*100)/100});}
          emit();
        }});
      let result;
      try {result=await current.run();}
      catch {result={...current.snapshot(),status:'uncertain'};}
      finally {current=null;}
      started+=result.started;budget-=result.started;
      outcomes.set(plan.id,{...result,summary:result.summary||outcomes.get(plan.id)?.summary,category:result.status});
      const finishedSummary=result.summary||outcomes.get(plan.id)?.summary;
      if(finishedSummary?.has_usable_knowledge&&!firstUsableAt.has(plan.id)){firstUsableAt.set(plan.id,perfNow());perf('material_first_usable',{source_id:plan.id,queue_position:index+1,elapsed_ms:Math.round((perfNow()-runStarted)*100)/100});}
      if(finishedSummary?.readiness==='ready'&&!readyAt.has(plan.id)){readyAt.set(plan.id,perfNow());perf('material_ready',{source_id:plan.id,queue_position:index+1,elapsed_ms:Math.round((perfNow()-runStarted)*100)/100,source_preparation_ms:Math.round((perfNow()-sourceStarted)*100)/100});}
      emit();
      // A confirmed provider outage applies to the current foreground
      // authorization. Keep later materials saved and not_started for an
      // explicit continuation after the provider is available again.
      if(['provider_unavailable','daily_allowance','allowance_unavailable','left','stopped'].includes(result.status)){
        status=result.status;break;
      }
      status='running';
    }
    if(left)status='left';
    else if(stopped)status='stopped';
    else if(status==='running'){
      const oneOutcome=ids.length===1?outcomes.get(ids[0]):null;
      if(oneOutcome&&['provider_unavailable','preparation_timeout','uncertain','failed','status_unavailable'].includes(oneOutcome.category))status=oneOutcome.category;
      else status=ids.length&&ids.every(id=>outcomes.get(id)?.summary?.readiness==='ready')?'completed':'incomplete';
    }
    let finalUsage;
    try {finalUsage=await api('/usage');} catch {/* Never infer exhaustion from an unavailable usage response. */}
    if(!left&&!stopped&&!['completed','provider_unavailable','preparation_timeout','uncertain','failed','status_unavailable'].includes(status)){
      if(finalUsage?.daily_limit_reached)status='daily_allowance';
      else if(finalUsage&&(finalUsage.paused||!availableAIAllowance(finalUsage)))status='allowance_unavailable';
    }
    for(const id of ids){
      const outcome=outcomes.get(id);
      if(!outcome)outcomes.set(id,{category:status,summary:null});
      else if(outcome.category==='not_started'&&status!=='provider_unavailable')outcome.category=status;
      else if(status==='daily_allowance'&&outcome.category==='completed'&&outcome.summary?.readiness!=='ready')outcome.category='daily_allowance';
    }
    if(ids.length>1&&!['provider_unavailable','left','stopped','daily_allowance','allowance_unavailable'].includes(status)){
      const failures=[...outcomes.values()].filter(outcome=>['provider_unavailable','preparation_timeout','failed','uncertain','status_unavailable'].includes(outcome.category));
      if(failures.length)status='incomplete';
    }
    if(callbackFailure)status='status_unavailable';
    if(!['completed','incomplete'].includes(status))perf('preparation_interruption',{reason:status,completed_work:snapshot().completedWork});
    perf('preparation_batch_complete',{selected_count:ids.length,status,duration_ms:Math.round((perfNow()-runStarted)*100)/100});
    emit();return snapshot();
  }
  return {snapshot,run:()=>promise??=execute(),stop(reason='user'){
    stopped=true;if(reason==='navigation')left=true;if(reason==='callback_failure')callbackFailure=true;current?.stop();
  }};
}
