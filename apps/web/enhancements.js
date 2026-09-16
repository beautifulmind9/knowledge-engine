const QUICK_KNOWLEDGE_QUESTIONS = [
  "What does this source teach?",
  "What concepts appear in this source?",
  "What problems does this source help solve?",
  "What did this chapter teach?",
  "What examples support this idea?",
  "What decision rules can I apply?",
];

let pendingKnowledgeQuestion = null;
let decorating = false;

// app.js currently builds the Workshop payload without the dynamically added
// output_format field. Keep the enhancement layer responsible for forwarding
// the selected format until the base Workshop form is consolidated.
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init = {}) => {
  const path = typeof input === "string" ? input : input?.url || "";
  const isWorkshopRequest =
    path === "/workshops/prepare" || path === "/workshops/generate";

  if (isWorkshopRequest && typeof init.body === "string") {
    try {
      const payload = JSON.parse(init.body);
      const selectedFormat = document
        .querySelector('#ke-output-format-host select[name="output_format"]')
        ?.value?.trim();

      if (selectedFormat && !payload.output_format) {
        payload.output_format = selectedFormat;
        init = { ...init, body: JSON.stringify(payload) };
      }
    } catch {
      // Leave non-JSON or malformed requests untouched; the normal request
      // path will surface the underlying validation error.
    }
  }

  return nativeFetch(input, init);
};

function makeElement(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function currentViewTitle() {
  return document.querySelector("#main h1")?.textContent?.trim() || "";
}

function selectedKnowledgeSourceId() {
  const searchForm = document.querySelector("#main > form");
  return searchForm?.querySelector("select")?.value || "";
}

function openKnowledgeQuestion(question) {
  const chapter = document.querySelector("#ke-chapter-scope")?.value?.trim() || "";
  const scopedQuestion = chapter
    ? `${question}\nChapter or section: ${chapter}`
    : question;

  pendingKnowledgeQuestion = {
    question: scopedQuestion,
    sourceId: selectedKnowledgeSourceId(),
  };

  document.querySelector('nav button[data-view="workshop"]')?.click();
}

function decorateKnowledgeView() {
  if (document.querySelector("#ke-ask-card")) return;

  const main = document.querySelector("#main");
  const searchForm = main?.querySelector(":scope > form");
  if (!main || !searchForm) return;

  const card = makeElement("section", undefined, "card");
  card.id = "ke-ask-card";
  card.append(
    makeElement("h3", "Ask this knowledge"),
    makeElement(
      "p",
      "Use the selected source or current library as evidence. These questions open a grounded Knowledge answer / synthesis in Workshop."
    )
  );

  const chapterLabel = makeElement("label", "Chapter / section — optional");
  const chapterInput = document.createElement("input");
  chapterInput.id = "ke-chapter-scope";
  chapterInput.placeholder = "e.g. Chapter 3, Simple";
  chapterLabel.append(chapterInput);
  card.append(chapterLabel);

  const quickActions = makeElement("div", undefined, "actions");
  for (const question of QUICK_KNOWLEDGE_QUESTIONS) {
    const button = makeElement("button", question);
    button.type = "button";
    button.addEventListener("click", () => openKnowledgeQuestion(question));
    quickActions.append(button);
  }
  card.append(quickActions);

  const askForm = document.createElement("form");
  const askLabel = makeElement("label", "Ask my knowledge");
  const askInput = document.createElement("input");
  askInput.name = "knowledge_question";
  askInput.required = true;
  askInput.minLength = 2;
  askInput.placeholder = "Ask a question across the selected source or library";
  askLabel.append(askInput);
  const askButton = makeElement("button", "Use in Workshop", "primary");
  askButton.type = "submit";
  askForm.append(askLabel, askButton);
  askForm.addEventListener("submit", event => {
    event.preventDefault();
    openKnowledgeQuestion(askInput.value.trim());
  });
  card.append(askForm);

  searchForm.after(card);
}

function applyPendingKnowledgeQuestion() {
  if (!pendingKnowledgeQuestion) return;

  const form = document.querySelector("#main section.card form");
  if (!form) return;

  const situation = form.elements.namedItem("situation");
  const goal = form.elements.namedItem("goal");
  const outputType = form.elements.namedItem("Output type");
  const sources = form.elements.namedItem(
    "Sources — optional; use Ctrl / Command to select several"
  );

  if (!situation || !goal || !outputType || !sources) return;

  situation.value = pendingKnowledgeQuestion.question;
  goal.value = pendingKnowledgeQuestion.question;
  outputType.value = "knowledge_answer";
  outputType.dispatchEvent(new Event("change", { bubbles: true }));

  if (pendingKnowledgeQuestion.sourceId) {
    for (const option of sources.options) {
      option.selected = option.value === pendingKnowledgeQuestion.sourceId;
    }
  }

  pendingKnowledgeQuestion = null;
}

function clearLegacyFormatConstraint(constraints) {
  const prefix = "Output format: ";
  const lines = constraints.value
    .split("\n")
    .filter(line => line.trim() && !line.startsWith(prefix));
  constraints.value = lines.join("\n");
}

async function decorateWorkshopView() {
  if (document.querySelector("#ke-output-format-host")) {
    applyPendingKnowledgeQuestion();
    return;
  }

  const form = document.querySelector("#main section.card form");
  if (!form) return;

  const outputType = form.elements.namedItem("Output type");
  const constraints = form.elements.namedItem("constraints");
  if (!outputType || !constraints) return;

  const response = await fetch("/outputs/modes");
  if (!response.ok) return;
  const data = await response.json();
  const modes = new Map(data.items.map(mode => [mode.id, mode]));

  const host = document.createElement("div");
  host.id = "ke-output-format-host";
  outputType.closest("label")?.after(host);

  const renderFormat = () => {
    host.replaceChildren();
    clearLegacyFormatConstraint(constraints);

    const mode = modes.get(outputType.value);
    const formats = mode?.formats || [];
    if (!formats.length) return;

    const label = makeElement("label", "Format");
    const select = document.createElement("select");
    select.name = "output_format";
    select.append(new Option("Choose a format", ""));
    for (const format of formats) select.append(new Option(format, format));
    label.append(select);
    host.append(label);
  };

  outputType.addEventListener("change", renderFormat);
  renderFormat();
  applyPendingKnowledgeQuestion();
}

async function decorateCurrentView() {
  if (decorating) return;
  decorating = true;
  try {
    const title = currentViewTitle();
    if (title === "Ideas you can put to work.") {
      decorateKnowledgeView();
    } else if (title === "What are you working on?") {
      await decorateWorkshopView();
    }
  } finally {
    decorating = false;
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
