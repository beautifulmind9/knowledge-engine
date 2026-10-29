// Read-only text preview: the caller supplies the existing API and view guard.
export function mountSourceSearch(root,{sourceId,api,isActive=()=>true}){
 const doc=root.ownerDocument,make=(tag,text)=>{const n=doc.createElement(tag);if(text)n.textContent=text;return n;};
 const panel=make('details'),label=make('summary','Search original text · no AI'),query=make('input'),go=make('button','Find passages'),results=make('div');
 query.type='search';query.maxLength=2000;query.setAttribute('aria-label','Search this material’s original text');
 go.type='button';results.setAttribute('aria-live','polite');
 panel.append(label,make('p','Search readable source text without building knowledge. Matches may miss paraphrases and important details.'),query,go,results);root.append(panel);
 let revision=0;
 const run=async()=>{const text=query.value.trim();if(!text)return;const ticket=++revision;go.disabled=true;results.replaceChildren(make('p','Searching source text…'));
  try{const data=await api(`/source-search?${new URLSearchParams({q:text,source_id:sourceId,limit:'5',neighbors:'true'})}`);if(!isActive()||ticket!==revision)return;
   results.replaceChildren(make('p',data.count?'Ranked passages · not a completeness assessment.':'No text matches found. This does not mean the material has no answer.'));
   if(data.query_terms_limited)results.append(make('p','This bounded search used the first 64 distinct meaningful terms. Try a shorter request for a different focus.'));
   for(const coverage of data.coverage||[]){results.append(make('p',coverage.status==='indexed_text'?'Readable text indexed for this search.':coverage.status==='preserved_not_indexed'?'Original preserved; readable text is not indexed. This preview does not process material.':'Extraction coverage is uncertain.'));
    if(coverage.no_text_pages?.length)results.append(make('p',`Pages without searchable text: ${coverage.no_text_pages.join(', ')}. Preserved images have not been interpreted.`));
    for(const note of coverage.limitations||[])results.append(make('p',note));}
   for(const item of data.items||[]){const article=make('article');article.append(make('h3',[item.title,item.section,item.page_start?`Page ${item.page_start}`:null].filter(Boolean).join(' · ')),make('blockquote',item.text));
    if(item.neighbors?.length){const context=make('details');context.append(make('summary','Nearby source context'));for(const n of item.neighbors)context.append(make('blockquote',n.text));article.append(context);}results.append(article);}
  }catch{if(isActive()&&ticket===revision)results.replaceChildren(make('p','Source search is unavailable. Existing knowledge workflows remain available.'));}finally{if(isActive()&&ticket===revision)go.disabled=false;}
 };
 go.onclick=run;query.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();run();}};query.oninput=()=>{revision++;go.disabled=false;results.replaceChildren();};
 return panel;
}
