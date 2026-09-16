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

function scopedKnowledgeQuestion(question) {
  const chapter = document.querySelector("#ke-chapter-scope")?.value?.trim() || "";
  return chapter
    ? `${question}\nChapter or section: ${chapter}`
    : question;
}

function openKnowledgeQuestionInWorkshop(question) {
  pendingKnowledgeQuestion = {
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

function renderKnowledgeAnswer(data, originalQuestion) {
  const existing = document.querySelector("#ke-knowledge-answer");
  const card = existing || makeElement("section", undefined, "card");
  card.id = "ke-knowledge-answer";
  card.replaceChildren();

  const output = data.output || {};
  card.append(
    makeElement("h3", output.title || "Knowledge answer"),
    makeElement(
      "p",
      `Grounded answer · ${data.knowledge_unit_count || 0} retrieved knowledge units · not saved automatically`,
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
    card.append(detail(`Applied knowledge (${applied.length})`, appliedList));
  }

  if ((output.design_choices || []).length) {
    card.append(detail("Design choices / synthesis", list(output.design_choices)));
  }

  card.append(
    actions(
      button("Open in Workshop", () => openKnowledgeQuestionInWorkshop(originalQuestion))
    )
  );

  if (!existing) {
    document.querySelector("#ke-ask-card")?.after(card);
  }

  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function generateKnowledgeAnswer(question, trigger) {
  const scopedQuestion = scopedKnowledgeQuestion(question);
  let card = document.querySelector("#ke-knowledge-answer");
  if (!card) {
    card = makeElement("section", undefined, "card");
    card.id = "ke-knowledge-answer";
    document.querySelector("#ke-ask-card")?.after(card);
  }

  card.replaceChildren(
    makeElement("h3", "Generating grounded answer…"),
    makeElement("p", "Using the selected Knowledge scope. This is one explicit Gemini request.", "muted")
  );

  if (trigger) trigger.disabled = true;

  try {
    const response = await fetch("/workshops/generate", {
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
        source_ids: selectedKnowledgeSourceIds(),
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

    renderKnowledgeAnswer(await response.json(), question);
  } catch (error) {
    card.replaceChildren(
      makeElement("h3", "Knowledge answer could not be generated"),
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
    makeElement("h3", "Ask this knowledge"),
    makeElement(
      "p",
      "Ask a grounded question about the selected source or current library. Answers appear here using one explicit Gemini request and are not saved automatically."
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
    const quickButton = makeElement("button", question);
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
  askInput.placeholder = "Ask a question across the selected source or library";
  askLabel.append(askInput);
  const askButton = makeElement("button", "Ask knowledge", "primary");
  askButton.type = "submit";
  askForm.append(askLabel, askButton);
  askForm.addEventListener("submit", event => {
    event.preventDefault();
    generateKnowledgeAnswer(askInput.value.trim(), askButton);
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

  const selected = new Set(pendingKnowledgeQuestion.sourceIds || []);
  if (selected.size) {
    for (const option of sources.options) {
      option.selected = selected.has(option.value);
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
