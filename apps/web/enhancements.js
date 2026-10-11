import {apiFetch} from './api.js';
import { scopeQuestion } from './knowledge-browser.js';

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

let pendingKnowledgeQuestion = null;
let decorating = false;
let decorationPending = false;
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

function list(items) {
  const node = document.createElement("ul");
  for (const item of items) node.append(makeElement("li", item));
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

function currentViewTitle() {
  return document.querySelector("#main h1")?.textContent?.trim() || "";
}

function selectedKnowledgeSourceIds() {
  const searchForm = document.querySelector("#main > form");
  const sourceSelect = searchForm?.querySelector("select");
  if (!sourceSelect) return [];

  if (sourceSelect.value) return [sourceSelect.value];

  // When the user is viewing all sources in the current library, the source
  // selector contains exactly that visible scope. Passing those IDs keeps a
  // direct Knowledge answer inside the same scope without needing app.js state.
  return [...sourceSelect.options]
    .map(option => option.value)
    .filter(Boolean);
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
  pendingKnowledgeQuestion = context || {
    question: scopedKnowledgeQuestion(question),
    sourceIds: selectedKnowledgeSourceIds(),
  };

  document.querySelector('nav button[data-view="workshop"]')?.click();
}

function findKnowledgeUnitTitle(snapshot, assetId) {
  for (const group of snapshot || []) {
    if (
      group?.canonical_asset?.id === assetId ||
      (group?.asset_ids || []).includes(assetId)
    ) {
      return group.canonical_asset?.title || assetId;
    }
  }
  return assetId;
}

function knowledgeAnswerCard() {
  let card = document.querySelector("#ke-knowledge-answer");
  if (!card) {
    card = makeElement("section", undefined, "card");
    card.id = "ke-knowledge-answer";
    document.querySelector("#ke-ask-card")?.after(card);
  }
  return card;
}

function showKnowledgeScopePrompt(title, message, inputSelector) {
  const card = knowledgeAnswerCard();
  card.replaceChildren(
    makeElement("h3", title),
    makeElement("p", message, "muted")
  );
  document.querySelector(inputSelector)?.focus();
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

function validateKnowledgeQuestionScope(question) {
  if (question === CHAPTER_QUESTION && !document.querySelector('#ke-source-scope')?.value) {
    showKnowledgeScopePrompt("Choose one material first", "Choose a material before asking about its chapter. No Gemini request was used.", "#ke-source-scope");
    return false;
  }
  if (question === CHAPTER_QUESTION && !knowledgeScopeValue("#ke-chapter-scope")) {
    showKnowledgeScopePrompt(
      "Choose a chapter or section first",
      "Enter the chapter or section above, then ask the chapter question again. No Gemini request was used.",
      "#ke-chapter-scope"
    );
    return false;
  }

  if (question === IDEA_EXAMPLES_QUESTION && !knowledgeScopeValue("#ke-idea-scope")) {
    showKnowledgeScopePrompt(
      "Name the idea first",
      "Enter the idea or concept you want examples for, then ask the examples question again. No Gemini request was used.",
      "#ke-idea-scope"
    );
    return false;
  }

  return true;
}

function renderKnowledgeAnswer(data, originalQuestion, context) {
  const card = knowledgeAnswerCard();
  card.replaceChildren();

  const output = data.output || {};
  card.append(
    makeElement("h3", output.title || "Answer from your library"),
    makeElement(
      "p",
      `Grounded answer · ${data.knowledge_unit_count || 0} useful ideas · not saved automatically`,
      "muted"
    )
  );

  const content = makeElement("div", output.content || "No answer returned.");
  content.style.whiteSpace = "pre-wrap";
  card.append(content);

  const applied = output.applied_knowledge || [];
  if (applied.length) {
    const appliedList = document.createElement("ul");
    for (const reference of applied) {
      appliedList.append(
        makeElement(
          "li",
          `${findKnowledgeUnitTitle(data.knowledge_snapshot, reference.asset_id)} — ${reference.usage_note}`
        )
      );
    }
    card.append(detail(`Ideas and evidence used (${applied.length})`, appliedList));
  }

  if ((output.design_choices || []).length) {
    card.append(detail("Design choices / synthesis", list(output.design_choices)));
  }

  card.append(
    actions(
      button("Open in Create", () => openKnowledgeQuestionInWorkshop(originalQuestion, context))
    )
  );

  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function generateKnowledgeAnswer(question, trigger) {
  if (!validateKnowledgeQuestionScope(question)) return;

  const sourceIds = selectedKnowledgeSourceIds();
  if (!sourceIds.length) {
    showKnowledgeScopePrompt("No materials in scope", "Add a prepared material before asking. No Gemini request was used.", "#ke-source-scope");
    return;
  }
  const scopedQuestion = scopedKnowledgeQuestion(scopeQuestion(question, !!document.querySelector('#ke-source-scope')?.value));
  const ticket = ++answerRevision;
  const card = knowledgeAnswerCard();

  card.replaceChildren(
    makeElement("h3", "Generating grounded answer…"),
    makeElement("p", "Using the selected materials. This is one explicit Gemini request.", "muted")
  );

  if (trigger) trigger.disabled = true;

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
    renderKnowledgeAnswer(data, question, {question: scopedQuestion, sourceIds});
  } catch (error) {
    if (ticket !== answerRevision || !card.isConnected) return;
    card.replaceChildren(
      makeElement("h3", "Answer could not be generated"),
      makeElement("p", error.message || String(error), "error")
    );
  } finally {
    if (trigger) trigger.disabled = false;
  }
}

function decorateKnowledgeView() {
  if (document.querySelector("#ke-ask-card")) return;

  const main = document.querySelector("#main");
  const searchForm = main?.querySelector(":scope > form");
  if (!main || !searchForm) return;

  const card = makeElement("section", undefined, "card");
  card.id = "ke-ask-card";
  card.append(
    makeElement("h3", "Ask your library"),
    makeElement(
      "p",
      "Ask a grounded question about the selected material or current library. Answers appear here using one explicit Gemini request and are not saved automatically."
    )
  );

  const chapterLabel = makeElement(
    "label",
    "Chapter / section — required for the chapter question"
  );
  const chapterInput = document.createElement("input");
  chapterInput.id = "ke-chapter-scope";
  chapterInput.placeholder = "e.g. Chapter 3, Simple";
  chapterLabel.append(chapterInput);
  card.append(chapterLabel);

  const ideaLabel = makeElement(
    "label",
    "Idea / concept — required for the examples question"
  );
  const ideaInput = document.createElement("input");
  ideaInput.id = "ke-idea-scope";
  ideaInput.placeholder = "e.g. keeping workshops interactive";
  ideaLabel.append(ideaInput);
  card.append(ideaLabel);

  const quickActions = makeElement("div", undefined, "actions");
  for (const question of QUICK_KNOWLEDGE_QUESTIONS) {
    const quickButton = makeElement("button", scopeQuestion(question, !!document.querySelector('#ke-source-scope')?.value).replaceAll('sources','materials').replaceAll('source','material'));
    quickButton.dataset.question = question;
    quickButton.type = "button";
    quickButton.addEventListener("click", () =>
      generateKnowledgeAnswer(question, quickButton)
    );
    quickActions.append(quickButton);
  }
  card.append(quickActions);

  const askForm = document.createElement("form");
  const askLabel = makeElement("label", "Ask my knowledge");
  const askInput = document.createElement("input");
  askInput.name = "knowledge_question";
  askInput.required = true;
  askInput.minLength = 2;
  askInput.placeholder = "Ask a question across the selected material or library";
  askLabel.append(askInput);
  const askButton = makeElement("button", "Ask your library", "primary");
  askButton.type = "submit";
  askForm.append(askLabel, askButton);
  askForm.addEventListener("submit", event => {
    event.preventDefault();
    generateKnowledgeAnswer(askInput.value.trim(), askButton);
  });
  card.append(askForm);

  const refreshScope = () => {
    if (!card.isConnected) return;
    const single = !!document.querySelector('#ke-source-scope')?.value;
    for (const node of quickActions.children) node.textContent = scopeQuestion(node.dataset.question, single).replaceAll('sources','materials').replaceAll('source','material');
    card.querySelector('h3').textContent = single ? 'Ask this material' : 'Ask these materials';
  };
  searchForm.addEventListener('change', refreshScope);
  for (const input of [chapterInput, ideaInput]) input.addEventListener('input', () => {
    answerRevision++;
    document.querySelector('#ke-knowledge-answer')?.remove();
  });
  searchForm.after(card);
  refreshScope();
}

function applyPendingKnowledgeQuestion() {
  if (!pendingKnowledgeQuestion) return;
  const form = document.querySelector('#create-brief');
  if (!form?.seedInteraction) return;
  const pending = pendingKnowledgeQuestion;
  pendingKnowledgeQuestion = null;
  form.seedInteraction(pending.question, pending.sourceIds || []);
}

async function decorateCurrentView() {
  if (decorating) { decorationPending = true; return; }
  decorating = true;
  try {
    const title = currentViewTitle();
    if (title === "Ideas you can put to work.") {
      decorateKnowledgeView();
    } else if (title === "What are you working on?") {
      applyPendingKnowledgeQuestion();
    }
  } finally {
    decorating = false;
    if (decorationPending) { decorationPending = false; queueMicrotask(decorateCurrentView); }
  }
}

const main = document.querySelector("#main");
if (main) {
  const observer = new MutationObserver(() => {
    queueMicrotask(decorateCurrentView);
  });
  observer.observe(main, { childList: true, subtree: true });
  decorateCurrentView();
}
