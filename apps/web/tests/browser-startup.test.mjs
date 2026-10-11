import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';

// Execute intact ES modules, including imports and startup, in an isolated process.
// The view tests intentionally slice out startup and cannot detect module failures.
test('shell modules initialize Home without requests or runtime errors', () => {
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
    import assert from 'node:assert/strict';
    import {readFileSync} from 'node:fs';
    const html=readFileSync('apps/web/index.html','utf8');
    const observers=[];
    class Element {
      constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.dataset={};this.textContent='';}
      append(...nodes){this.children.push(...nodes);this.notify();}
      replaceChildren(...nodes){this.children=[];this.append(...nodes);}
      setAttribute(key,value){this.attributes[key]=value;}
      removeAttribute(key){delete this.attributes[key];}
      querySelector(selector){return selector==='#beta-logout'?this.children.find(n=>n.id==='beta-logout')||null:null;}
      focus(){document.activeElement=this;}
      notify(){for(const observer of observers)if(observer.target===this)queueMicrotask(observer.callback);}
    }
    const main=new Element('main'),feedback=new Element('div'),body=new Element('body');
    const nav=[...html.matchAll(/<(a|button)\\b[^>]*data-view="([^"]+)"[^>]*>/g)].map(([,tag,view])=>{const node=new Element(tag);node.dataset.view=view;return node;});
    globalThis.document={body,cookie:'',
      querySelector(selector){if(selector==='main'||selector==='#main')return main;if(selector==='#feedback')return feedback;if(selector==='#main h1')return main.children.find(n=>n.tag==='h1')||null;return null;},
      querySelectorAll(selector){return selector==='[data-view]'?nav:selector==='nav button'?nav.filter(n=>n.tag==='button'):[];},
      createElement:tag=>new Element(tag),addEventListener(){}};
    globalThis.window=globalThis;
    globalThis.location={hash:''};
    globalThis.history={replaceState(_state,_title,hash){location.hash=hash;},pushState(_state,_title,hash){location.hash=hash;}};
    globalThis.addEventListener=()=>{};
    globalThis.MutationObserver=class {constructor(callback){this.callback=callback;}observe(target){this.target=target;observers.push(this);}};
    globalThis.fetch=()=>{throw Error('Home startup must not make requests');};
    const scripts=[...html.matchAll(/<script type="module" src="[/]static[/]([^"]+)"/g)].map(match=>match[1]);
    assert.equal(scripts.length,3);
    for(const script of scripts)await import(new URL('./apps/web/'+script, 'file://'+process.cwd()+'/'));
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(document.querySelector('#main h1')?.textContent,'What would you like to do?');
    const choices=main.children.find(n=>n.className==='home-choices');
    assert.deepEqual(choices.children.map(n=>n.children[0].textContent),['Add to my library','Continue my work']);
    assert.equal(feedback.textContent,'');
    assert.equal(document.activeElement,main);
    assert.ok(nav.every(n=>typeof n.onclick==='function'));
    await nav.find(n=>n.dataset.view==='home').onclick({preventDefault(){}});
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(document.querySelector('#main h1')?.textContent,'What would you like to do?');
    assert.equal(feedback.textContent,'');
  `], {cwd:new URL('../../..',import.meta.url),encoding:'utf8'});
  assert.equal(result.status,0,result.stdout+result.stderr);
});
