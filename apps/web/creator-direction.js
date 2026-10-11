import {restoreCreateFields} from './create-draft.js';
export function splitDirectionLines(value = "") {
  return value
    .split("\n")
    .map(item => item.trim())
    .filter(Boolean);
}

export function mergeCreatorDirection(payload, direction = {}) {
  const next = { ...payload };
  const creativeIntent = direction.creative_intent?.trim();
  const creatorContext = direction.creator_context?.trim();
  const preserve = Array.isArray(direction.preserve)
    ? direction.preserve.filter(Boolean)
    : splitDirectionLines(direction.preserve || "");
  const avoid = Array.isArray(direction.avoid)
    ? direction.avoid.filter(Boolean)
    : splitDirectionLines(direction.avoid || "");

  if (creativeIntent) next.creative_intent = creativeIntent;
  if (creatorContext) next.creator_context = creatorContext;
  if (preserve.length) next.preserve = preserve;
  if (avoid.length) next.avoid = avoid;
  return next;
}

export function creatorDirectionFromRoot(root = document) {
  return {
    creative_intent:
      root.querySelector('[name="creative_intent"]')?.value || "",
    creator_context:
      root.querySelector('[name="creator_context"]')?.value || "",
    preserve: root.querySelector('[name="preserve"]')?.value || "",
    avoid: root.querySelector('[name="avoid"]')?.value || "",
  };
}

function makeField(labelText, name, placeholder) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const input = document.createElement("textarea");
  input.name = name;
  input.rows = 3;
  input.placeholder = placeholder;
  label.append(input);
  return label;
}

export function decorateCreatorDirection(root = document) {
  if (root.querySelector("#ke-creator-direction")) return false;
  const form = root.querySelector("#main section.card form");
  if (!form || root.querySelector("#main h1")?.textContent?.trim() !== "What are you working on?") {
    return false;
  }

  const tone = form.elements.namedItem("tone_or_style");
  if (!tone) return false;

  const details = document.createElement("details");
  details.id = "ke-creator-direction";
  const summary = document.createElement("summary");
  summary.textContent = "Creator direction — optional";
  const note = document.createElement("p");
  note.className = "muted";
  note.textContent =
    "Use this when something about your intent, voice, visual language or existing work should shape the result. Leave it blank when it is not relevant; Create should not invent a style for you.";

  details.append(
    summary,
    note,
    makeField(
      "What are you going for?",
      "creative_intent",
      "e.g. intimate, imperfect and nostalgic rather than conventionally cinematic"
    ),
    makeField(
      "What about you or this project matters?",
      "creator_context",
      "e.g. this is a personal birthday memory, not branded content"
    ),
    makeField(
      "What should Create preserve? — one per line",
      "preserve",
      "e.g. handheld movement\nlong pause before the final line"
    ),
    makeField(
      "What should Create avoid? — one per line",
      "avoid",
      "e.g. overly polished language\ngeneric cinematic transitions"
    )
  );

  tone.closest("label")?.after(details);
  restoreCreateFields(form, ["creative_intent", "creator_context", "preserve", "avoid"]);
  return true;
}
