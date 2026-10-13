import {apiFetch} from './api.js';
import { scopeQuestion } from './knowledge-browser.js';
import {renderGroundedAnswer, renderGroundedInline, createAnswerEvidenceIndex, observeAnswerTableOverflow} from './answer-renderer.js';
import {beginProcessingStatus,endProcessingStatus,announceProcessingStatus} from './processing-status.js';

const QUICK_KNOWLEDGE_QUESTIONS = [
  "What does this source teach?",
  "What concepts appear in this source?",
  "What problems does this source help solve?",
  "What did this chapter teach?",
  "What examples support this idea?",
  "What decision rules can I apply?",
];

const CHAPTER_QUESTION = "What did this chapter teach?";
const IDEA_EXAMPLES_QUESTION = "What examples support this idea?";

let answerRevision = 0;
document.addEventListener("ke-scope-change", () => {
  answerRevision++;
  document.querySelector("#ke-knowledge-answer")?.remove();
});

function makeElement(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

// enhancements.js is loaded as its own ES module. Helpers declared inside
// app.js are therefore not visible here, so keep this module self-contained.
function detail(title, ...nodes) {
  const node = document.createElement("details");
  node.append(makeElement("summary", title), ...nodes);
  return node;
}

function actions(...nodes) {
  const wrapper = makeElement("div", undefined, "actions");
  wrapper.append(...nodes);
  return wrapper;
}

function button(text, action, className = "") {
  const node = makeElement("button", text, className);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

function selectedKnowledgeSourceIds() {
  return document.querySelector('#main')?.exploreContext?.sourceIds() || [];
}

function knowledgeScopeValue(id) {
  return document.querySelector(id)?.value?.trim() || "";
}

function scopedKnowledgeQuestion(question) {
  const chapter = knowledgeScopeValue("#ke-chapter-scope");
  const idea = knowledgeScopeValue("#ke-idea-scope");
  const scopeLines = [];
  if (chapter) scopeLines.push(`Chapter or section: ${chapter}`);
  if (idea) scopeLines.push(`Idea or concept: ${idea}`);
  return scopeLines.length ? `${question}\n${scopeLines.join("\n")}` : question;
}

function openKnowledgeQuestionInWorkshop(question, context = null) {
  const scope=context || {question:scopedKnowledgeQuestion(question),sourceIds:selectedKnowledgeSourceIds()};
  return document.querySelector('#main')?.exploreContext?.handoff(scope.question,scope.sourceIds);
}

function knowledgeAnswerCard() {
  let card = document.querySelector("#ke-knowledge-answer");
  if (!card) {
    card = makeElement("section", undefined, "card grounded-answer");
    card.id = "ke-knowledge-answer";
    document.querySelector("#ke-search-form")?.after(card);
  }
  return card;
}

function showKnowledgeScopePrompt(title, message, inputSelector) {
  const card = knowledgeAnswerCard();
  card.replaceChildren(
    makeElement("h3", title),
    makeElement("p", message, "muted")
  );
  const target=document.querySelector(inputSelector);
  if(target?.closest('details')){target.closest('details').open=true;target.closest('label').hidden=false;}
  target?.focus();
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function validateKnowledgeQuestionScope(question) {
  if ((question === CHAPTER_QUESTION || document.querySelector('#main')?.exploreContext?.state?.promptMode === 'section') && !document.querySelector('#ke-source-scope')?.value) {
    showKnowledgeScopePrompt("Choose one material first", "Choose a material before asking about its chapter. No AI request was made.", "#ke-source-scope");
    return false;
  }
  if ((question === CHAPTER_QUESTION || document.querySelector('#main')?.exploreContext?.state?.promptMode === 'section') && !knowledgeScopeValue("#ke-chapter-scope")) {
    showKnowledgeScopePrompt(
      "Choose a chapter or section first",
      "Enter the chapter or section above, then ask the chapter question again. No AI request was made.",
      "#ke-chapter-scope"
    );
    return false;
  }

  if ((question === IDEA_EXAMPLES_QUESTION || document.querySelector('#main')?.exploreContext?.state?.promptMode === 'idea') && !knowledgeScopeValue("#ke-idea-scope")) {
    showKnowledgeScopePrompt(
      "Name the idea first",
      "Enter the idea or concept you want examples for, then ask the examples question again. No AI request was made.",
      "#ke-idea-scope"
    );
    return false;
  }

  return true;
}

function renderKnowledgeAnswer(data, originalQuestion, context) {
  const card = knowledgeAnswerCard();
  card.replaceChildren();
  const localResults = document.querySelector('#ke-search-results');
  if (localResults) localResults.hidden = true;

  const output = data.output || {};
  const snapshot = data.knowledge_snapshot || [];
  const scopeIds = context?.sourceIds || [];
  const sourceInfo = (document.querySelector('#main')?.exploreContext?.sourceInfo?.() || []).filter(source => scopeIds.includes(source.id));
  const evidenceIndex = createAnswerEvidenceIndex(snapshot, sourceInfo);
  const count = Number.isInteger(data.knowledge_unit_count) ? data.knowledge_unit_count : snapshot.length;
  const scopeLabel = document.querySelector('#main')?.exploreContext?.scopeLabel?.() || 'your selected materials';
  const answerTitle = makeElement("h2", undefined, "answer-title");
  card.append(
    answerTitle,
    makeElement("p", `Grounded in ${count} ${count === 1 ? 'idea' : 'ideas'} from ${scopeLabel}`, "answer-grounding"),
    makeElement("p", "Not saved automatically", "answer-save-note")
  );
  answerTitle.append(renderGroundedInline(output.title || "Answer from your library", {document, snapshot, sourceInfo}));
  const evidenceBase = data.evidence_base;
  if (evidenceBase?.selected_count) {
    const {selected_count:selected,ready_count:ready,preparing_count:preparing,attention_count:attention,unavailable_count:unavailable} = evidenceBase;
    const pieces = [`${selected} selected ${selected===1?'material':'materials'}`, `${ready} ready`];
    if (preparing) pieces.push(`${preparing} still preparing`);
    if (attention) pieces.push(`${attention} needs attention`);
    if (unavailable) pieces.push(`${unavailable} unavailable`);
    const base = makeElement('p', `Evidence base · ${pieces.join(' · ')}`, 'answer-evidence-base');
    card.insertBefore(base, card.children[2] || null);
    if (preparing || attention || unavailable) {
      const note = preparing && !attention && !unavailable
        ? 'This answer reflects the knowledge currently available. More may appear as the remaining material is prepared.'
        : 'This answer reflects the knowledge currently available; some selected material is not fully available.';
      card.insertBefore(makeElement('p', note, 'answer-evidence-limit'), card.children[3] || null);
    }
  }

  let content;
  if (Array.isArray(output.reasoning_sections) && output.reasoning_sections.length) {
    const useWorkspaceGrid = output.reasoning_sections.length >= 6;
    content = makeElement('article', undefined, `answer-document answer-reasoning-document${useWorkspaceGrid ? ' answer-reasoning-document--workspace-grid' : ''}`);
    const labels = {
      source_principle:'Source principle', source_tactic:'Source tactic', mechanism:'Underlying mechanism',
      interpretation:'KE interpretation', assumption:'Assumption', experiment:'Experiment',
      challenge:'Challenge / alternative', agreement:'Where sources agree', disagreement:'Disagreement',
      applicability:'Applicability', open_question:'Open question', analysis:'Analysis',
    };
    const tones = {source_principle:'source',source_tactic:'source',mechanism:'source',interpretation:'inference',assumption:'uncertain',experiment:'action',challenge:'warning',agreement:'source',disagreement:'warning',applicability:'uncertain',open_question:'uncertain'};
    for (const section of output.reasoning_sections) {
      const block = makeElement('section', undefined, `answer-reasoning-section answer-reasoning-${section.kind}`);
      block.append(makeElement('span', labels[section.kind] || 'Analysis', `answer-label answer-label-${tones[section.kind] || 'neutral'}`));
      const sectionTitle = makeElement('h3', undefined, 'answer-section-title');
      sectionTitle.append(renderGroundedInline(section.heading, {document, snapshot, sourceInfo}));
      block.append(sectionTitle);
      const body = renderGroundedAnswer(section.content, {document, snapshot, sourceInfo});
      block.append(...Array.from(body.childNodes));
      const sourceLabels = [...new Set((section.supporting_asset_ids || []).map(assetId => evidenceIndex.asset(assetId).label).filter(label => label && label !== 'Source & evidence'))];
      if (sourceLabels.length) block.append(makeElement('p', `From ${sourceLabels.join('; ')}`, 'answer-section-sources'));
      content.append(block);
    }
  } else content = renderGroundedAnswer(output.content || "No answer returned.", {document, snapshot, sourceInfo});
  card.append(content);

  const applied = output.applied_knowledge || [];
  if (applied.length) {
    const appliedList = document.createElement("ul");
    for (const reference of applied) {
      const item = document.createElement('li');
      const title = makeElement('strong', evidenceIndex.assetTitle(reference.asset_id));
      item.append(title);
      if (reference.usage_note) { const note = makeElement('p', undefined, 'answer-usage-note'); note.append(renderGroundedInline(reference.usage_note, {document, snapshot, sourceInfo})); item.append(note); }
      const evidence = evidenceIndex.asset(reference.asset_id);
      if (evidence.evidence.length) appendEvidence(item, evidence, 'Source & evidence', evidenceIndex);
      appliedList.append(item);
    }
    card.append(detail(`Ideas and evidence used (${applied.length})`, appliedList));
  }

  if ((output.design_choices || []).length) {
    const choices = document.createElement('ul');
    for (const choice of output.design_choices) {
      const item = document.createElement('li');
      item.append(...Array.from(renderGroundedAnswer(choice, {document, snapshot, sourceInfo}).childNodes));
      choices.append(item);
    }
    card.append(detail("Design choices / synthesis", choices));
  }

  card.append(
    actions(
      button("Open in Create", () => openKnowledgeQuestionInWorkshop(originalQuestion, context))
    )
  );
  card._answerTableObserver?.disconnect();
  card._answerTableObserver = observeAnswerTableOverflow(card);

  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function appendEvidence(parent, evidence, label, identityIndex) {
  const node = document.createElement('details'); node.className = 'answer-evidence';
  node.append(makeElement('summary', label));
  for (const entry of evidence.evidence) {
    const block = document.createElement('blockquote');
    const sourceLabel = entry.source_id ? identityIndex.source(entry.source_id).label : '';
    const context = [sourceLabel === 'Source & evidence' ? '' : sourceLabel, entry.chapter_or_section].filter(Boolean).join(' · ');
    if (context) block.append(makeElement('span', context, 'answer-evidence-context'));
    const quote = makeElement('p'); quote.append(renderGroundedInline(entry.evidence || '')); block.append(quote);
    node.append(block);
  }
  parent.append(node);
}

async function generateKnowledgeAnswer(question, trigger) {
  if (!validateKnowledgeQuestionScope(question)) return;

  const sourceIds = selectedKnowledgeSourceIds();
  if (!sourceIds.length) {
    showKnowledgeScopePrompt("No materials in scope", "Add a prepared material before asking. No AI request was made.", "#ke-source-scope");
    return;
  }
  const scopedQuestion = scopedKnowledgeQuestion(scopeQuestion(question, !!document.querySelector('#ke-source-scope')?.value));
  const viewState=document.querySelector('#main')?.exploreContext?.state;
  const ticket = ++answerRevision;
  const card = knowledgeAnswerCard();

  card.setAttribute('aria-busy','true');
  card.replaceChildren(makeElement("p", "Your grounded answer will appear here.", "muted"));

  if (trigger) trigger.disabled = true;
  const processing=beginProcessingStatus({label:'Thinking with your materials',detail:'Your question is being considered against the selected knowledge.'});

  try {
    const response = await apiFetch("/workshops/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        situation: scopedQuestion,
        goal: scopedQuestion,
        audience: null,
        constraints: [
          "Use only the selected knowledge scope as the evidence base",
          "Distinguish source-grounded teaching from generator synthesis",
        ],
        tone_or_style: "Clear, concise, practical",
        output_type: "knowledge_answer",
        output_format: null,
        source_ids: sourceIds,
        library_id: null,
        asset_ids: [],
        limit: 8,
        save: false,
      }),
    });

    if (!response.ok) {
      let error;
      try {
        error = await response.json();
      } catch {
        error = { detail: `Request failed (${response.status})` };
      }
      throw new Error(
        typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail)
      );
    }

    const data = await response.json();
    if (ticket !== answerRevision || !card.isConnected) return;
    card.removeAttribute('aria-busy');
    if(viewState)viewState.answer={data,question,context:{question:scopedQuestion,sourceIds}};
    renderKnowledgeAnswer(data, question, {question: scopedQuestion, sourceIds});
    announceProcessingStatus('Your grounded answer is ready.');
  } catch (error) {
    if (ticket !== answerRevision || !card.isConnected) return;
    card.removeAttribute('aria-busy');
    announceProcessingStatus('Your grounded answer could not be generated.');
    card.replaceChildren(
      makeElement("h3", "Answer could not be generated"),
      makeElement("p", error.message || String(error), "error")
    );
  } finally {
    endProcessingStatus(processing);
    if (trigger) trigger.disabled = false;
  }
}

function decorateKnowledgeView() {
  if (document.querySelector('#ke-ask-card')) return;
  const main=document.querySelector('#main'),viewState=main?.exploreContext?.state;
  const searchForm=main?.querySelector('#ke-search-form');
  if(!searchForm||!viewState)return;
  const request=searchForm.elements.namedItem('q');
  const askButton=button('Ask across sources',()=>{
    if(request.value.trim().length<2){request.reportValidity();return;}
    generateKnowledgeAnswer(request.value,askButton);
  },'primary');
  request.required=true;request.minLength=2;
  document.querySelector('#explore-actions').append(askButton);
  const sourceScope=document.querySelector('#ke-source-scope');
  const updateAskLabel=()=>{askButton.textContent=sourceScope?.value?'Ask this material':'Ask across sources';};
  sourceScope?.addEventListener('change',updateAskLabel);updateAskLabel();
  const actionNote=makeElement('p','Asking uses AI. Find matching ideas searches prepared knowledge locally.','muted');
  actionNote.className='explore-action-note';
  document.querySelector('#explore-actions').after(actionNote);
  const findButton=document.querySelector('#explore-actions button[type="submit"]');
  if(findButton){findButton.textContent='Find matching ideas';findButton.className='';}
  const optional=makeElement('div');optional.id='ke-ask-card';optional.className='explore-options';
  const suggestions=detail('Try a question');suggestions.className='question-suggestions';
  const prompts=makeElement('div');prompts.className='prompt-options';
  const context=detail('Add context');context.id='explore-context';context.open=!!viewState.contextOpen;
  const chapterLabel=makeElement('label','Chapter or section'),chapterInput=makeElement('input');
  chapterInput.id='ke-chapter-scope';chapterInput.value=viewState.chapter;chapterInput.placeholder='e.g. Practice, Chapter 3';chapterLabel.append(chapterInput);
  const ideaLabel=makeElement('label','Idea or concept'),ideaInput=makeElement('input');
  ideaInput.id='ke-idea-scope';ideaInput.value=viewState.idea;ideaInput.placeholder='e.g. Practice breaks';ideaLabel.append(ideaInput);
  const note=makeElement('p','Context guides the question; it does not restrict evidence to that chapter or section.','muted');
  context.append(chapterLabel,ideaLabel,note);
  function refreshContext(){
    chapterLabel.hidden=viewState.contextMode==='idea';ideaLabel.hidden=viewState.contextMode==='section';
    context.open=!!viewState.contextOpen;
    const values=[viewState.chapter,viewState.idea].filter(Boolean);
    context.querySelector('summary').textContent=values.length?'Context · '+values.join(' · '):'Add context';
  }
  function invalidateAnswer(){answerRevision++;viewState.answer=null;document.querySelector('#ke-knowledge-answer')?.remove();document.querySelector('#create-handoff')?.remove();}
  const labels=['What does this teach?','Concepts','Problems','Ask about a section','Examples','Decision rules'];
  QUICK_KNOWLEDGE_QUESTIONS.forEach((question,index)=>{
    const prompt=button(labels[index],()=>{
      request.value=scopeQuestion(question,!!document.querySelector('#ke-source-scope')?.value);
      request.dispatchEvent(new Event('input',{bubbles:true}));
      viewState.promptMode=question===CHAPTER_QUESTION?'section':question===IDEA_EXAMPLES_QUESTION?'idea':null;
      viewState.contextMode=viewState.promptMode||'both';
      viewState.contextOpen=!!viewState.promptMode||!!(viewState.chapter||viewState.idea);
      suggestions.open=false;refreshContext();
      if(viewState.promptMode==='section')chapterInput.focus();else if(viewState.promptMode==='idea')ideaInput.focus();else request.focus();
    });
    prompts.append(prompt);
  });
  suggestions.append(prompts);optional.append(suggestions,context);searchForm.append(optional);
  context.addEventListener('toggle',()=>{viewState.contextOpen=context.open;});
  context.querySelector('summary').addEventListener('click',()=>{if(!context.open){viewState.contextMode='both';chapterLabel.hidden=false;ideaLabel.hidden=false;}});
  for(const input of [chapterInput,ideaInput])input.addEventListener('input',()=>{
    viewState.chapter=chapterInput.value;viewState.idea=ideaInput.value;invalidateAnswer();refreshContext();
  });
  request.addEventListener('input',()=>{viewState.promptMode=null;viewState.query=request.value;invalidateAnswer();});
  const capture=main.captureExplore;
  main.captureExplore=()=>{capture?.();viewState.chapter=chapterInput.value;viewState.idea=ideaInput.value;viewState.contextOpen=context.open;};
  main.exploreContext.configureIdea=title=>{
    request.value=IDEA_EXAMPLES_QUESTION;request.dispatchEvent(new Event('input',{bubbles:true}));
    viewState.idea=title;viewState.promptMode='idea';viewState.contextMode='idea';viewState.contextOpen=true;
    ideaInput.value=title;refreshContext();request.focus();
  };
  refreshContext();
  if(viewState.answer){const a=viewState.answer;renderKnowledgeAnswer(a.data,a.question,a.context);}
}

document.addEventListener('ke-explore-ready',decorateKnowledgeView);
