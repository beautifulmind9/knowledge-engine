// Presentation state only. Strict Workshop/KnowledgeAsset models remain authoritative.
// Interpretation is conservative and local: no network, IDs from prose, or hidden AI.
/**
 * @typedef {'explicit'|'inferred'|'suggested'|'user-corrected'} Provenance
 * @typedef {'resolved'|'ambiguous'|'missing-essential'|'optional-unset'} Resolution
 * @typedef {{value: *, provenance: Provenance, resolution: Resolution}} InterpretedValue
 * @typedef {Object} InteractionDraft
 * @property {string} originalRequest Exact capture, never replaced by a summary.
 * @property {number} revision Monotonic identity for material edits.
 * @property {string|null} interpretedRequest Request version last reviewed locally.
 * @property {Object<string, InterpretedValue>} values Task, result and direction/context values.
 * @property {InterpretedValue} scope Application-owned library/material/idea selections.
 * @property {{state: string, items: Array}} clarification Local unresolved material questions.
 * @property {{state: string, snapshot: Object|null}} confirmation Execution snapshot.
 * @property {Object|null} prepared Revision, payload identity and evidence preview.
 */
const optional = value => ({value, provenance:'suggested', resolution:'optional-unset'});
const material = (value, provenance='explicit', resolution='resolved') => ({value, provenance, resolution});
const arrayFields = new Set(['constraints','preserve','avoid']);
/** @returns {InteractionDraft} */
export function newInteractionDraft(originalRequest='') {
  return {originalRequest, revision:0, interpretedRequest:null,
    values:{task:optional(''),situation:optional(''),goal:optional(''),audience:optional(''),
      constraints:optional([]),tone_or_style:optional(''),output_type:optional(''),output_format:optional(''),
      creative_intent:optional(''),creator_context:optional(''),preserve:optional([]),avoid:optional([])},
    scope:material({libraryId:null,sourceIds:[],assetIds:[]},'suggested'),
    clarification:{state:'none',items:[]}, confirmation:{state:'unconfirmed',snapshot:null}, prepared:null};
}
export function invalidateDraft(draft) {
  return {...draft, revision:draft.revision+1, prepared:null, confirmation:{state:'unconfirmed',snapshot:null}};
}
export function captureRequest(draft, originalRequest) {
  if (draft.originalRequest===originalRequest) return draft;
  return {...invalidateDraft(draft),originalRequest,clarification:{state:'none',items:[]}};
}
export function correctDraft(draft, name, value) {
  const next=invalidateDraft(draft);
  if(name==='scope'||name==='output_type'){
    const items=next.clarification.items.filter(i=>i.field!==name);
    next.clarification={state:items.length?'needed':'none',items};
  }
  if(name==='scope') return {...next,scope:material(value,'user-corrected')};
  if(arrayFields.has(name)&&typeof value==='string')value=value.split('\n').map(s=>s.trim()).filter(Boolean);
  if(name==='output_type'&&!value)next.clarification={state:'needed',items:[...next.clarification.items,{field:name,message:'Choose a result.'}]};
  return {...next,values:{...next.values,[name]:material(value,'user-corrected',value?.length?'resolved':(['task','goal','output_type'].includes(name)?'missing-essential':'optional-unset'))}};
}
// Keep entire clauses (including negation). Never rewrite a creator's instruction.
function clauses(request) {return request.match(/[^\n.!?;]+[.!?;]?/g)?.map(s=>s.trim()).filter(Boolean)||[];}
function labeled(request, label) {
  return request.match(new RegExp('(?:^|[\\n.;])\\s*(?:'+label+')\\s*:\\s*([^\\n;]+)','i'))?.[1]?.trim()||'';
}
function positiveClauses(request) {
  return clauses(request).map(s=>s.split(/\b(?:avoid|do not|don['’]t|without|not|never|no)\b/i)[0].trim()).filter(Boolean);
}
function substantiveTask(request) {
  const parts=positiveClauses(request);
  return parts.find(s=> /^(?:please\s+)?(?:write|draft|edit|design|create|make|plan|compare|explain|summarize|synthesize|decide|build)\b/i.test(s))
    || parts.find(s=>! /^(?:use|using|from|based on|draw on|only|keep|preserve|retain|audience\s*:|context\s*:|tone\s*:|style\s*:|direction\s*:|budget\s*:)/i.test(s)) || request;
}
function proposedMode(request, modes) {
  // Negative clauses cannot choose a result family ("do not make a presentation").
  const positive=positiveClauses(request).join(' ');
  const choices=[['workshop_plan',/\bworkshop\b/i],['study_guide',/\b(?:study guide|study|learn)\b/i],
    ['decision_brief',/\b(?:decide|decision)\b/i],['social_content',/\b(?:linkedin|instagram|carousel|social|thread)\b/i],
    ['presentation',/\b(?:presentation|slides|talking points)\b/i],['playbook',/\b(?:playbook|process)\b/i],
    ['action_plan',/\baction plan\b/i],['research_synthesis',/\b(?:research|compare|synthesize)\b/i],
    ['knowledge_answer',/\b(?:what|why|how|explain)\b/i],['writing',/\b(?:write|essay|email|edit|draft)\b/i]];
  const matches=choices.filter(([id,re])=>modes.some(m=>m.id===id)&&re.test(positive));
  const specific=matches.filter(([id])=>!['writing','knowledge_answer'].includes(id));
  const id=specific.length===1?specific[0][0]:specific.length>1?null:
    matches.find(([id])=>id==='writing')?.[0]||matches.find(([id])=>id==='knowledge_answer')?.[0];
  return material(id||'','suggested',id?'resolved':'missing-essential');
}
function scopeNameMatch(text, name) {
  const escaped=name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return new RegExp('\\b(?:use|using|from|based on|draw on|only)\\s+(?:(?:the|my|our)\\s+)?["“]?'+escaped+'["”]?(?:\\s+library)?(?=$|[.;!?]|\\s+(?:to|for)\\b)','i').test(text);
}
function interpretedScope(request, catalog, previous) {
  if(previous.provenance==='user-corrected') return previous;
  const hints=clauses(request).filter(s=>/\b(?:use|using|from|based on|draw on|only|exclude)\b/i.test(s)&&
    (/\b(?:books?|sources?|materials?|librar(?:y|ies)|notes|reports?)\b/i.test(s)||/["“][^"”]+["”]/.test(s)||
      catalog.sources.some(item=>scopeNameMatch(s,item.title))||catalog.libraries.some(item=>scopeNameMatch(s,item.name))));
  if(!hints.length)return previous;
  const text=hints.join(' ');
  const exclusion=/\b(?:except|exclude|not|without|never|avoid|don['’]t)\b/i.test(text);
  if(!exclusion&&hints.length===1&&/\b(?:all|whole|entire) (?:my |the )?(?:librar(?:y|ies)|materials|sources)\b/i.test(text))return material({libraryId:null,sourceIds:[],assetIds:[]});
  const sources=catalog.sources.filter(s=>scopeNameMatch(text,s.title));
  const libraries=catalog.libraries.filter(l=>scopeNameMatch(text,l.name));
  // Resolve a unique complete title only. Partial names and exclusions need a local choice.
  if(hints.length===1&&sources.length===1&&!libraries.length&&!exclusion&&!/\b(?:and|both)\b/i.test(text))
    return material({libraryId:null,sourceIds:[sources[0].id],assetIds:[]});
  if(hints.length===1&&libraries.length===1&&!sources.length&&!exclusion&&!/\b(?:and|both)\b/i.test(text))
    return material({libraryId:libraries[0].id,sourceIds:[],assetIds:[]});
  return {...previous,resolution:'ambiguous'};
}

export function interpretDraft(draft, catalog) {
  const request=draft.originalRequest;
  if(request.trim().length<2)throw Error('Tell us a little about what you want to do. Your request has been kept.');
  const parts=clauses(request);
  const proposed={task:material(substantiveTask(request),'inferred'),situation:material(request),goal:material(request),
    audience:optional(labeled(request,'audience')),constraints:material(parts.filter(s=>!(/\b(?:preserve|keep|retain)\b/i.test(s))&&(/\b(?:must|only|under|at most|no more|exactly|minutes?|words?|budget)\b/i.test(s)||/[$£€]\s*\d/.test(s)))),
    tone_or_style:optional(labeled(request,'tone|style')),output_type:proposedMode(request,catalog.modes),output_format:optional(''),
    creative_intent:optional(labeled(request,'direction|creative intent')),creator_context:optional(labeled(request,'creator context|context')),
    preserve:material(parts.filter(s=>/\b(?:preserve|keep|retain)\b/i.test(s))),
    avoid:material(parts.filter(s=>/\b(?:avoid|do not|don['’]t|without|never|no)\b/i.test(s)))};
  const requestedFormat=catalog.modes.find(m=>m.id===proposed.output_type.value)?.formats?.filter(format=>positiveClauses(request).join(' ').toLowerCase().includes(format.toLowerCase()))||[];
  if(requestedFormat.length===1)proposed.output_format=material(requestedFormat[0]);
  for(const [name,item] of Object.entries(proposed)) {
    if(!item.value?.length&&name!=='output_type')item.resolution='optional-unset';
    else if(item.provenance==='suggested'&&name!=='output_type')item.provenance='explicit';
    if(draft.values[name]?.provenance==='user-corrected')proposed[name]=draft.values[name];
  }
  let scope=interpretedScope(request,catalog,draft.scope);
  if((scope.value.libraryId&&!catalog.libraries.some(l=>l.id===scope.value.libraryId))||scope.value.sourceIds.some(id=>!catalog.sources.some(s=>s.id===id&&(!scope.value.libraryId||s.library_id===scope.value.libraryId))))scope={...scope,resolution:'ambiguous'};
  const items=scope.resolution==='ambiguous'?[{field:'scope',message:'Which materials did you mean? Choose below, or search across your library.'}]:[];
  if(!proposed.output_type.value)items.push({field:'output_type',message:'What would you like to make? Choose a result so we can find relevant knowledge.'});
  return {...invalidateDraft(draft),interpretedRequest:request,values:proposed,scope,
    clarification:{state:items.length?'needed':'none',items}};
}
export function draftNeedsInterpretation(draft) {return draft.interpretedRequest!==draft.originalRequest;}
// The sole Create -> Workshop adapter. Scope is application-owned, never interpreted IDs.
export function workshopRequest(draft, catalog) {
  if(draftNeedsInterpretation(draft))throw Error('Review your updated request before creating.');
  if(draft.clarification.state==='needed'||draft.scope.resolution==='ambiguous')throw Error('Choose which materials you mean before continuing.');
  const v=Object.fromEntries(Object.entries(draft.values).map(([k,x])=>[k,x.value]));
  const scope=draft.scope.value;
  if(scope.libraryId&&!catalog.libraries.some(l=>l.id===scope.libraryId))throw Error('That library is no longer available. Choose another.');
  if(scope.sourceIds.some(id=>!catalog.sources.some(s=>s.id===id&&(!scope.libraryId||s.library_id===scope.libraryId))))throw Error('A selected material is no longer available in this library. Choose again.');
  if(scope.assetIds.some(id=>!catalog.selectedAssetIds.includes(id)))throw Error('Choose those ideas again from your library.');
  if(!catalog.modes.some(m=>m.id===v.output_type))throw Error('Choose a result type.');
  if(String(v.task).trim().length<2)throw Error('What do you want to do? Edit the task.');
  if(String(v.goal).trim().length<2)throw Error('What should the result help you do? Edit the goal.');
  const corrections=Object.entries(draft.values).filter(([,item])=>item.provenance==='user-corrected').map(([key,item])=>`${key.replaceAll('_',' ')}: ${Array.isArray(item.value)?item.value.join('; '):item.value||'(unset)'}`);
  // Original request remains exact, including details not recognized by the local interpreter.
  const situation=draft.originalRequest+(corrections.length?'\n\nReviewed corrections take precedence over the original wording for these items:\n'+corrections.join('\n'):'');
  return {interaction_revision:draft.revision,situation,goal:v.goal,audience:v.audience||null,constraints:v.constraints,tone_or_style:v.tone_or_style||null,
    output_type:v.output_type,output_format:v.output_format||null,creative_intent:v.creative_intent||null,
    creator_context:v.creator_context||null,preserve:v.preserve,avoid:v.avoid,
    library_id:scope.libraryId,source_ids:[...scope.sourceIds],asset_ids:[...scope.assetIds],save:true};
}
export function evidenceIdentity(draft, payload) {return JSON.stringify([draft.revision,payload]);}
export function confirmDraft(draft, payload) {
  return {...draft,confirmation:{state:'confirmed',snapshot:{revision:draft.revision,identity:evidenceIdentity(draft,payload),payload:JSON.parse(JSON.stringify(payload))}}};
}
export function preparedGenerationRequest(draft, catalog) {
  const payload=workshopRequest(draft,catalog),prepared=draft.prepared;
  if(!prepared || prepared.revision!==draft.revision || prepared.identity!==evidenceIdentity(draft,payload) || !prepared.evidence.prepared_snapshot_id || prepared.evidence.interaction_revision!==draft.revision)
    throw Error('Update knowledge for this request before creating.');
  if(!prepared.evidence.knowledge_unit_count)throw Error('No relevant ideas found. Adjust your request or knowledge scope.');
  return {...payload,prepared_snapshot_id:prepared.evidence.prepared_snapshot_id};
}
