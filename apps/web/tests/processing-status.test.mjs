import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createProcessingStatusStore,attachProcessingAnnouncer,renderProcessingStatus} from '../processing-status.js';

test('application activity survives subscriber/view updates until the operation ends',()=>{
 const store=createProcessingStatusStore(),seen=[];store.subscribe(value=>seen.push(value));
 const id=store.begin({label:'Preparing your material',detail:'Saved progressively.'});
 store.update(id,{completed:2,total:8});
 assert.equal(store.get().id,id);assert.equal(store.get().completed,2);assert.equal(store.get().total,8);
 assert.equal(store.end(id),true);assert.equal(store.get(),null);assert.equal(seen.length,4);
});

test('a stale operation cannot clear a newer activity',()=>{
 const store=createProcessingStatusStore(),old=store.begin({label:'Reading your material'}),current=store.begin({label:'Creating your draft'});
 assert.equal(store.end(old),false);assert.equal(store.get().id,current);assert.equal(store.get().label,'Creating your draft');
});

test('a foreground preparation exposes one persistent stop control after navigation',()=>{
 const stopped=[],store=createProcessingStatusStore(),id=store.begin({label:'Preparing your library',detail:'1 of 3 materials ready.',onStop:()=>stopped.push('stop')});
 const nodes=new Map();
 const create=()=>({className:'',attrs:{},classList:{add(){},remove(){}},setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},append(...children){for(const child of children)if(child.className)nodes.set('.'+child.className,child);}});
 const root={hidden:true,ownerDocument:{createElement:create},setAttribute(){},replaceChildren(...children){for(const child of children)if(child.className)nodes.set('.'+child.className,child);},querySelector(selector){return nodes.get(selector)||null;}};
 renderProcessingStatus(root,store.get());
 const stop=nodes.get('.processing-status-stop');assert.equal(root.hidden,false);assert.equal(stop.hidden,false);assert.equal(stop.textContent,'Stop preparation');
 stop.onclick();assert.deepEqual(stopped,['stop']);
 store.update(id,{stopRequested:true,onStop:null,detail:'Finishing the current step before stopping.'});renderProcessingStatus(root,store.get());
 assert.equal(stop.hidden,false);assert.equal(stop.textContent,'Stopping safely…');assert.equal(stop.disabled,true);
});

test('accessible activity announcements change at meaningful states, not every progress increment',()=>{
 const announcements=[],announcer={set textContent(value){if(value)announcements.push(value);}};
 const element=()=>({hidden:false,attrs:{},classList:{add(){},remove(){}},setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},append(){},querySelector(){return null;}});
 const children=new Map(),root={hidden:true,ownerDocument:{createElement:element},setAttribute(){},replaceChildren(node){this.child=node;},querySelector(selector){return children.get(selector)||null;}};
 // The renderer's created tree is represented by named nodes for progress semantics.
 const originalCreate=root.ownerDocument.createElement;root.ownerDocument.createElement=()=>{const node=originalCreate();node.append=(...nodes)=>{for(const child of nodes){if(child.className)children.set('.'+child.className,child);}};return node;};
 attachProcessingAnnouncer(announcer);
 renderProcessingStatus(root,{id:1,label:'Preparing your material',detail:'New knowledge appears as it becomes available.',completed:1,total:8});
 const meter=children.get('.processing-status-meter');assert.equal(meter.attrs['aria-valuenow'],'13');
 renderProcessingStatus(root,{id:1,label:'Preparing your material',detail:'New knowledge appears as it becomes available.',completed:2,total:8});
 assert.equal(announcements.length,1);
 renderProcessingStatus(root,{id:1,label:'Preparation paused',detail:'The AI service was temporarily unavailable.',completed:2,total:8});
 assert.equal(announcements.length,2);assert.match(announcements[1],/AI service was temporarily unavailable/);
});
