export function createProcessingStatusStore(){
 let nextId=0,current=null;const listeners=new Set();
 const publish=()=>{for(const listener of listeners)listener(current);};
 return {
  get:()=>current,
  subscribe(listener){listeners.add(listener);listener(current);return()=>listeners.delete(listener);},
  begin({label,detail='',completed=null,total=null,onStop=null}={}){const id=++nextId;current={id,label,detail,completed,total,onStop,state:'running'};publish();return id;},
  update(id,patch={}){if(current?.id!==id||current.state!=='running')return false;current={...current,...patch};publish();return true;},
  end(id){if(current?.id!==id)return false;current=null;publish();return true;},
 };
}

const appProcessingStatus=createProcessingStatusStore();
let processingAnnouncer=null;
export const attachProcessingAnnouncer=node=>{processingAnnouncer=node;};
export const announceProcessingStatus=text=>{if(processingAnnouncer&&text)processingAnnouncer.textContent=text;};
export const getProcessingStatus=()=>appProcessingStatus.get();
export const subscribeProcessingStatus=listener=>appProcessingStatus.subscribe(listener);
export const beginProcessingStatus=details=>appProcessingStatus.begin(details);
export const updateProcessingStatus=(id,patch)=>appProcessingStatus.update(id,patch);
export const endProcessingStatus=id=>appProcessingStatus.end(id);

export function renderProcessingStatus(root,status){
 if(!root)return;
 root.hidden=!status;
 if(!status){root.replaceChildren();root._processingId=null;root._announcementKey='';return;}
 const announcementKey=`${status.label||'Working'}\u0000${status.detail||''}`;
 if(announcementKey!==root._announcementKey){root._announcementKey=announcementKey;announceProcessingStatus([status.label,status.detail].filter(Boolean).join('. '));}
 root.setAttribute('data-run-id',String(status.id));
 const doc=root.ownerDocument;
 if(root._processingId!==status.id){
  const row=doc.createElement('div');row.className='processing-status-row';
  const copy=doc.createElement('div');copy.className='processing-status-copy';
  const label=doc.createElement('strong');label.className='processing-status-label';
  const detail=doc.createElement('span');detail.className='processing-status-detail';
  const meter=doc.createElement('progress');meter.className='processing-status-meter';meter.setAttribute('aria-label','Work progress');
  const percentage=doc.createElement('span');percentage.className='processing-status-percentage';
  const stop=doc.createElement('button');stop.className='processing-status-stop';stop.type='button';
  row.append(copy,meter,percentage,stop);copy.append(label,detail);root.replaceChildren(row);root._processingId=status.id;
 }
 const label=root.querySelector('.processing-status-label'),detail=root.querySelector('.processing-status-detail'),meter=root.querySelector('.processing-status-meter'),percentage=root.querySelector('.processing-status-percentage'),stop=root.querySelector('.processing-status-stop');
 label.textContent=status.label||'Working';detail.textContent=status.detail||'';
 stop.hidden=typeof status.onStop!=='function'&&!status.stopRequested;stop.textContent=status.stopRequested?'Stopping safely…':'Stop preparation';stop.disabled=!!status.stopRequested;stop.onclick=typeof status.onStop==='function'?status.onStop:null;
 const determinate=Number.isFinite(status.completed)&&Number.isFinite(status.total)&&status.total>0;
 meter.hidden=false;percentage.hidden=!determinate;
 if(!determinate){meter.removeAttribute('value');meter.classList.add('processing-indeterminate');}
 if(determinate){const value=Math.max(0,Math.min(100,Math.round(100*status.completed/status.total)));meter.classList.remove('processing-indeterminate');meter.max=100;meter.value=value;meter.setAttribute('role','progressbar');meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax','100');meter.setAttribute('aria-valuenow',String(value));meter.setAttribute('aria-valuetext',`${value}% complete`);percentage.textContent=`${value}%`;}
}
