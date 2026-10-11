import {test} from 'node:test';
import assert from 'node:assert/strict';
import {newInteractionDraft,captureRequest,correctDraft,interpretDraft,workshopRequest,confirmDraft,evidenceIdentity,preparedGenerationRequest} from '../interaction-draft.js';
const catalog={modes:[{id:'writing'},{id:'workshop_plan'},{id:'presentation'},{id:'decision_brief'}],libraries:[{id:'l1',name:'Reading'}],sources:[{id:'s1',title:'Facilitator notes',library_id:'l1'},{id:'s2',title:'Other notes',library_id:'l1'}],selectedAssetIds:['a1']};
const interpret=request=>interpretDraft(newInteractionDraft(request),catalog);
test('detailed request stays exact, with explicit constraints, negation and preserve instructions',()=>{
 const request='  Design a 90 minute workshop for new managers.\nKeep the long opening pause; avoid role play. Do not exceed $200. Work without slides.\nAudience: team leads\nDirection: intimate and imperfect\nContext: a personal project  ';
 const draft=interpret(request),payload=workshopRequest(draft,catalog);
 assert.equal(draft.originalRequest,request);assert.equal(payload.situation,request);assert.equal(payload.goal,request);
 assert.equal(payload.output_type,'workshop_plan');assert.ok(payload.constraints.includes('Do not exceed $200.'));
 assert.ok(payload.preserve.includes('Keep the long opening pause;'));assert.ok(payload.avoid.includes('avoid role play.'));
 assert.ok(payload.avoid.includes('Work without slides.'));assert.equal(payload.creative_intent,'intimate and imperfect');assert.equal(payload.audience,'team leads');
});
test('negative mention of result type cannot select it',()=>{
 assert.equal(interpret('Write an essay. Do not create a presentation.').values.output_type.value,'writing');
});
test('user corrections, including deliberately cleared values, override subsequent inference',()=>{
 let draft=interpret('Write an essay. Preserve the long pauses. Avoid jargon.');
 draft=correctDraft(draft,'preserve','Keep only the ending');draft=correctDraft(draft,'avoid','');draft=correctDraft(draft,'goal','Explain my experience');
 draft=interpretDraft(captureRequest(draft,'Write an essay. Preserve all pauses. Avoid short words.'),catalog);
 const payload=workshopRequest(draft,catalog);
 assert.deepEqual(payload.preserve,['Keep only the ending']);assert.deepEqual(payload.avoid,[]);assert.equal(payload.goal,'Explain my experience');
 assert.equal(draft.values.preserve.provenance,'user-corrected');assert.ok(payload.situation.includes('Reviewed corrections take precedence'));
});
test('ambiguous, duplicate, partial and excluded source matches never invent or silently broaden IDs',()=>{
 for(const request of ['Use the leadership book to write an essay.','Use "imaginary-id".','Use all materials except Other notes.','Use Facilitator notes and Other notes.']){
  const draft=interpret(request);assert.equal(draft.scope.resolution,'ambiguous',request);assert.deepEqual(draft.scope.value.sourceIds,[]);
  assert.throws(()=>workshopRequest(draft,catalog),/Choose which materials/);
 }
 const duplicate={...catalog,sources:[...catalog.sources,{id:'s3',title:'Facilitator notes',library_id:'l1'}]};
 assert.equal(interpretDraft(newInteractionDraft('Use Facilitator notes.'),duplicate).scope.resolution,'ambiguous');
 assert.deepEqual(interpret('Use Facilitator notes. Write an essay.').scope.value.sourceIds,['s1']);
});
test('scope can only be resolved against current application data, and deliberate all-material choice resolves ambiguity',()=>{
 let draft=interpret('Use the leadership book. Write an essay.');
 assert.throws(()=>workshopRequest(correctDraft(draft,'scope',{libraryId:null,sourceIds:['invented'],assetIds:[]}),catalog),/no longer available/);
 assert.throws(()=>workshopRequest(correctDraft(draft,'scope',{libraryId:'invented',sourceIds:[],assetIds:[]}),catalog),/no longer available/);
 assert.throws(()=>workshopRequest(correctDraft(draft,'scope',{libraryId:null,sourceIds:[],assetIds:['invented']}),catalog),/Choose those ideas/);
 draft=correctDraft(draft,'scope',{libraryId:null,sourceIds:[],assetIds:[]});assert.deepEqual(workshopRequest(draft,catalog).source_ids,[]);
});
test('vague request asks only for consequential result, never an arbitrary family',()=>{
 const draft=interpret('Help me think this through');assert.equal(draft.clarification.state,'needed');assert.equal(draft.values.output_type.value,'');
 assert.equal(draft.values.output_type.provenance,'suggested');
 for(const name of ['audience','tone_or_style','creator_context','creative_intent'])assert.equal(draft.values[name].resolution,'optional-unset');
 assert.throws(()=>workshopRequest(draft,catalog),/Choose/);assert.equal(workshopRequest(correctDraft(draft,'output_type','writing'),catalog).audience,null);
});
test('task, scope and material constraint edits invalidate confirmation and prepared evidence identity',()=>{
 const initial=interpret('Write an essay');
 for(const [name,value] of [['task','Make a decision'],['constraints','At most 100 words'],['scope',{libraryId:'l1',sourceIds:['s1'],assetIds:['a1']}]] ){
  const payload=workshopRequest(initial,catalog),identity=evidenceIdentity(initial,payload);
  const confirmed={...confirmDraft(initial,payload),prepared:{identity,evidence:{}}};
  const edited=correctDraft(confirmed,name,value);
  assert.equal(edited.prepared,null);assert.equal(edited.confirmation.state,'unconfirmed');assert.equal(edited.confirmation.snapshot,null);assert.notEqual(evidenceIdentity(edited,workshopRequest(edited,catalog)),identity);
 }
 const changed=captureRequest(initial,'Different request');assert.throws(()=>workshopRequest(changed,catalog),/Review/);
});
test('all existing execution semantics pass through one adapter and snapshot is independent',()=>{
 let draft=interpret('Write an essay');
 for(const [name,value] of Object.entries({audience:'Friends',tone_or_style:'Personal',output_format:'Essay',creative_intent:'Imperfect',creator_context:'My own memory',preserve:['My voice'],avoid:['Jargon']}))draft=correctDraft(draft,name,value);
 draft=correctDraft(draft,'scope',{libraryId:'l1',sourceIds:['s1'],assetIds:['a1']});const payload=workshopRequest(draft,catalog);
 for(const key of ['audience','tone_or_style','output_format','creative_intent','creator_context','preserve','avoid'])assert.deepEqual(payload[key],draft.values[key].value);
 assert.deepEqual(payload.source_ids,['s1']);assert.deepEqual(payload.asset_ids,['a1']);assert.equal(payload.library_id,'l1');assert.equal(payload.save,true);
 const confirmed=confirmDraft(draft,payload);payload.constraints.push('Later mutation');assert.equal(confirmed.confirmation.snapshot.payload.constraints.length,0);
});
test('failed local interpretation preserves the original draft and makes no transport attempt',()=>{
 const draft=newInteractionDraft(' ');assert.throws(()=>interpretDraft(draft,catalog),/Tell us a little/);assert.equal(draft.originalRequest,' ');assert.equal(draft.revision,0);
});

test('clear explicit result format is retained without turning it into a retrieval constraint',()=>{
 const formats={...catalog,modes:[{id:'social_content',formats:['LinkedIn post','Carousel']}]};
 const draft=interpretDraft(newInteractionDraft('Write a LinkedIn post about practice breaks.'),formats),payload=workshopRequest(draft,formats);
 assert.equal(payload.output_format,'LinkedIn post');assert.equal(draft.values.output_format.provenance,'explicit');assert.deepEqual(payload.constraints,[]);
});
test('negative material direction and multiple unresolved material clauses stay ambiguous',()=>{
 for(const request of ["Don't use Facilitator notes.",'Never use Facilitator notes.','Avoid using Facilitator notes.','Use Facilitator notes. Draw on the leadership book too.'])assert.equal(interpret(request).scope.resolution,'ambiguous',request);
});
test('clearing essential task marks local resolution and blocks execution without optional questions',()=>{
 const draft=correctDraft(interpret('Write an essay'),'task','');assert.equal(draft.values.task.resolution,'missing-essential');assert.throws(()=>workshopRequest(draft,catalog),/Edit the task/);
});

test('a source title substring cannot silently resolve a different complete title',()=>{
 const data={...catalog,sources:[{id:'wrong',title:'notes',library_id:'l1'}]};
 assert.equal(interpretDraft(newInteractionDraft('Use leadership notes.'),data).scope.resolution,'ambiguous');
 assert.equal(interpret("Don't use all materials.").scope.resolution,'ambiguous');
});

test('substantive task follows scope instructions and keeps unrecognized prose intact',()=>{
 const text='Use Facilitator notes. Write an essay. Make it feel like a quiet conversation.';
 const draft=interpret(text);assert.equal(draft.values.task.value,'Write an essay.');
 assert.equal(workshopRequest(draft,catalog).situation,text);
});
test('negative result instructions cannot select a forbidden family or format',()=>{
 for(const text of ['Do not create a presentation.',"Don't make a presentation.",'Never create a presentation.','No presentation please.'])assert.equal(interpret(text).values.output_type.value,'');
 assert.equal(interpret('Write an essay without slides.').values.output_type.value,'writing');
 const formats={...catalog,modes:[{id:'writing',formats:['Email','Essay']}]};
 assert.equal(interpretDraft(newInteractionDraft('Write something. Do not write an Email.'),formats).values.output_format.value,'');
});
test('Create requires the exact current server-owned prepared evidence identity and revision',()=>{
 let draft=interpret('Write an essay');const payload=workshopRequest(draft,catalog);
 const evidence={prepared_snapshot_id:'opaque-server-snapshot-12345',interaction_revision:draft.revision,knowledge_unit_count:1};
 assert.throws(()=>preparedGenerationRequest(draft,catalog),/Update knowledge/);
 draft={...draft,prepared:{revision:draft.revision,identity:evidenceIdentity(draft,payload),evidence}};
 assert.equal(preparedGenerationRequest(draft,catalog).prepared_snapshot_id,evidence.prepared_snapshot_id);
 for(const [field,value] of [['task','Write something else'],['constraints',['Under 100 words']],['scope',{libraryId:null,sourceIds:['s1'],assetIds:[]}]])assert.throws(()=>preparedGenerationRequest(correctDraft(draft,field,value),catalog),/Update knowledge/);
 for(const prepared of [{...draft.prepared,revision:99},{...draft.prepared,identity:'different'},{...draft.prepared,evidence:{...evidence,interaction_revision:99}},{...draft.prepared,evidence:{...evidence,prepared_snapshot_id:null}}])assert.throws(()=>preparedGenerationRequest({...draft,prepared},catalog),/Update knowledge/);
});
test('competing substantive result families ask locally instead of choosing by ordering',()=>{
 const draft=interpret('Make a workshop and a presentation.');assert.equal(draft.values.output_type.value,'');assert.equal(draft.clarification.state,'needed');
 assert.equal(interpret('Write a workshop plan.').values.output_type.value,'workshop_plan');
});
