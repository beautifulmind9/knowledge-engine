import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const app=readFileSync(new URL('../app.js',import.meta.url),'utf8');
const implementation=app.slice(app.indexOf('async function moveMaterials('),app.indexOf('async function libraryView('));
class Node {
 constructor(tag,text){this.tag=tag;this.textContent=text;this.children=[];this.classList={toggle:()=>{}};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 insertBefore(node){this.children.unshift(node);}
 setAttribute(){} focus(){this.focused=true;}
}
const walk=node=>[node,...node.children.flatMap(walk)];
function fixture(fail=[]){
 const calls=[],navigation=[];let refreshes=0,active=true,hold=null;
 const sources=[{id:'one',title:'First',library_id:'a'},{id:'two',title:'Second',library_id:'a'}];
 const libs=[{id:'a',name:'Original'},{id:'b',name:'Destination'}];
 const el=(tag,text)=>new Node(tag,text);
 const ctx=vm.createContext({Set,Map,api:async(path,options)=>{calls.push({path,options});if(hold)await hold;if(fail.includes(path.split('/')[2]))throw Error('private failure');},el,field:(label,name)=>{const l=el('label',label),i=el('input');i.name=name;l.append(i);return [l,i];},select:(label,values)=>{const l=el('label',label),s=el('select');s.values=values;s.value='';l.append(s);return [l,s];},button:(text,onclick)=>Object.assign(el('button',text),{onclick}),actions:(...nodes)=>{const n=el('div');n.append(...nodes);return n;},list:items=>{const n=el('ul');n.append(...items.map(t=>el('li',t)));return n;},navigate:(...args)=>navigation.push(args),state:{}});
 vm.runInContext(implementation,ctx);
 const bulk=ctx.bulkMoveSurface(sources,libs,()=>active,async()=>{refreshes++;});
 const rows=sources.map(source=>{const row=el('article');bulk.attach(row,source);return row;});
 const find=text=>walk(bulk.surface).find(n=>n.textContent===text);
 const choose=()=>{for(const row of rows){const i=walk(row).find(n=>n.type==='checkbox');i.checked=true;i.onchange();}};
 const destination=()=>walk(bulk.surface).find(n=>n.tag==='select');
 return {ctx,bulk,rows,calls,navigation,find,choose,destination,refreshes:()=>refreshes,leave:()=>{active=false;},hold:promise=>{hold=promise;}};
}
test('multi-select previews once, cancel makes no writes, confirmation uses membership-only endpoint',async()=>{
 const f=fixture();assert.equal(f.find('Move selected').hidden,true);f.choose();assert.equal(f.find('2 selected').textContent,'2 selected');
 await f.find('Move selected').onclick();assert.equal(f.find('Confirm move').disabled,true);
 f.destination().value='b';f.destination().onchange();assert.ok(f.find('First · Original → Destination'));assert.ok(f.find('Second · Original → Destination'));
 await f.find('Cancel').onclick();assert.equal(f.calls.length,0);assert.ok(f.find('2 selected'));
 await f.find('Move selected').onclick();f.destination().value='b';f.destination().onchange();await f.find('Confirm move').onclick();
 assert.deepEqual(f.calls.map(c=>[c.path,c.options.method,c.options.body.library_id]),[['/sources/one/library','PUT','b'],['/sources/two/library','PUT','b']]);
 assert.equal(f.refreshes(),1);assert.ok(f.find('2 of 2 materials moved to Destination.'));assert.equal(f.find('Move selected').hidden,true);
 await f.find('View destination library').onclick();assert.equal(f.navigation[0][1].library,'b');
});
test('partial and complete failure retain unsuccessful selections and name affected materials',async()=>{
 for(const failed of [['two'],['one','two']]){
  const f=fixture(failed);f.choose();await f.find('Move selected').onclick();f.destination().value='b';f.destination().onchange();await f.find('Confirm move').onclick();
  assert.equal(f.refreshes(),1);assert.ok(f.find(`${failed.length} selected`));assert.ok(f.find(`${2-failed.length} of 2 materials moved to Destination.`));assert.ok(f.find('Second'));
 }
});
test('select all and clear do not call APIs; busy batch locks selection and ignores duplicate confirmation',async()=>{
 const f=fixture();const all=walk(f.bulk.surface).find(n=>n.name==='select_all');all.checked=true;all.onchange();assert.ok(f.find('2 selected'));
 await f.find('Clear selection').onclick();assert.ok(f.find('0 selected'));assert.equal(f.calls.length,0);f.choose();await f.find('Move selected').onclick();f.destination().value='b';f.destination().onchange();
 let release;f.hold(new Promise(resolve=>{release=resolve;}));const confirm=f.find('Confirm move'),pending=confirm.onclick();assert.equal(all.disabled,true);await confirm.onclick();assert.equal(f.calls.length,1);release();await pending;assert.equal(f.calls.length,2);
});
test('navigation does not update detached view, and already-in-destination items cause no writes',async()=>{
 const f=fixture();const results=await f.ctx.moveMaterials([{id:'same',library_id:'b'},{id:'a/b',library_id:'a'}],'b');assert.equal(results.length,2);assert.equal(f.calls[0].path,'/sources/a%2Fb/library');
 f.choose();await f.find('Move selected').onclick();f.destination().value='b';f.destination().onchange();f.leave();await f.find('Confirm move').onclick();assert.equal(f.refreshes(),0);
});
