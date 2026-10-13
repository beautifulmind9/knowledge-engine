import {availableAIAllowance, createKnowledgeBuild} from './knowledge-build.js';

// One foreground Add/Continue authorization. Nothing here survives a refresh.
export function createMaterialPreparation({sourceIds, api, onSource=async()=>{}, onProgress=()=>{}}) {
  const ids=[...new Set(sourceIds)], outcomes=new Map();
  let current=null, stopped=false, left=false, promise, status='idle', currentId=null;
  const snapshot=()=>({status,currentId,outcomes:new Map(outcomes),sourceIds:ids.slice()});
  async function execute(){
    status='running';
    let usage;
    try {usage=await api('/usage');} catch {
      status='allowance_unavailable';for(const id of ids)outcomes.set(id,{category:status,summary:null});
      onProgress(snapshot());return snapshot();
    }
    const plans=[];
    for(const id of ids){
      if(stopped||left)break;
      try{
        const summary=await api(`/sources/${encodeURIComponent(id)}/summary`);
        const remaining=Number.isInteger(summary.total_parts)&&Number.isInteger(summary.completed_parts)?Math.max(0,summary.total_parts-summary.completed_parts):0;
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
      try{await onSource(plan.id,index,plans.length);}catch{status='status_unavailable';break;}
      if(stopped||left)break;
      current=createKnowledgeBuild({sourceId:plan.id,remainingParts:plan.remaining,
        usage:{...usage,calls_today:Number(usage.calls_today)+started},authorizationLimit:budget,api,isActive:()=>!left,
        onProgress:progress=>{
          outcomes.set(plan.id,{category:'running',...progress});
          onProgress(snapshot());
        }});
      let result;
      try {result=await current.run();}
      catch {result={...current.snapshot(),status:'uncertain'};}
      finally {current=null;}
      started+=result.started;budget-=result.started;
      outcomes.set(plan.id,{...result,category:result.status});
      onProgress(snapshot());
      if(result.status!=='completed'){status=result.status;break;}
    }
    if(left)status='left';
    else if(stopped)status='stopped';
    else if(status==='running')status=plans.length&&outcomes.size&&plans.every(p=>outcomes.get(p.id)?.summary?.readiness==='ready')?'completed':'incomplete';
    let finalUsage;
    try {finalUsage=await api('/usage');} catch {/* Never infer exhaustion from an unavailable usage response. */}
    if(!left&&!stopped&&!['completed','uncertain','status_unavailable'].includes(status)){
      if(finalUsage?.daily_limit_reached)status='daily_allowance';
      else if(finalUsage&&(finalUsage.paused||!availableAIAllowance(finalUsage)))status='allowance_unavailable';
    }
    for(const id of ids){
      const outcome=outcomes.get(id);
      if(!outcome)outcomes.set(id,{category:status,summary:null});
      else if(outcome.category==='not_started'||id===currentId&&outcome.summary?.readiness!=='ready')outcome.category=status;
    }
    onProgress(snapshot());return snapshot();
  }
  return {snapshot,run:()=>promise??=execute(),stop(reason='user'){
    stopped=true;if(reason==='navigation')left=true;current?.stop();
  }};
}
