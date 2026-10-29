import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mountSourceSearch} from '../source-search.js';
class Node {constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this._text='';this.value='';this.ownerDocument=doc;} append(...n){this.children.push(...n);} replaceChildren(...n){this.children=n;this._text='';} setAttribute(n,v){this.attributes[n]=v;} set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}}
const doc={createElement:t=>new Node(t)};
const all=n=>[n,...n.children.flatMap(all)];
test('preview is optional and dispatches only bounded read-only source search',async()=>{
 const root=new Node('section'),calls=[];
 mountSourceSearch(root,{sourceId:'synthetic',api:async path=>{calls.push(path);return {count:1,coverage:[{status:'indexed_text',no_text_pages:[2],limitations:['Image content is not interpreted.']}],items:[{title:'Source',section:'Consent',page_start:1,text:'<script>untrusted data</script>',neighbors:[{text:'Nearby exception'}]}]};}});
 assert.equal(calls.length,0);
 const input=all(root).find(n=>n.tagName==='input'),button=all(root).find(n=>n.tagName==='button');input.value='consent';await button.onclick();
 assert.equal(calls.length,1);assert.match(calls[0],/^\/source-search\?/);assert.match(calls[0],/source_id=synthetic/);
 assert.match(root.textContent,/not a completeness assessment/);assert.match(root.textContent,/Nearby exception/);assert.match(root.textContent,/Pages without searchable text: 2/);
 assert.equal(all(root).filter(n=>n.tagName==='script').length,0);assert.match(root.textContent,/<script>/);
});
test('empty and stale responses do not imply absence of knowledge',async()=>{
 const root=new Node('section');let resolve;
 mountSourceSearch(root,{sourceId:'s',api:()=>new Promise(r=>resolve=r)});
 const input=all(root).find(n=>n.tagName==='input'),button=all(root).find(n=>n.tagName==='button');input.value='old';const pending=button.onclick();input.value='new';input.oninput();resolve({count:0,items:[]});await pending;
 assert.ok(!root.textContent.includes('No text matches'));
});

test('no-answer and bounded-query notices remain explicit',async()=>{
 const root=new Node('section');mountSourceSearch(root,{sourceId:'s',api:async()=>({count:0,items:[],query_terms_limited:true,coverage:[{status:'preserved_not_indexed',limitations:[]}]})});
 const input=all(root).find(n=>n.tagName==='input'),button=all(root).find(n=>n.tagName==='button');input.value='query';await button.onclick();
 assert.match(root.textContent,/does not mean the material has no answer/);assert.match(root.textContent,/first 64/);assert.match(root.textContent,/preview does not process/);
});
