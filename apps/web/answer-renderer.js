const LABEL_KIND = new Map([
  ['principle', 'source'], ['source principle', 'source'], ['source tactic', 'source'],
  ['adaptation', 'inference'], ['ke interpretation', 'inference'], ['underlying mechanism', 'source'],
  ['assumption', 'uncertain'], ['applicability', 'uncertain'],
  ['experiment', 'action'], ['measurement', 'action'], ['warning', 'warning'],
  ['challenge / alternative', 'warning'], ['disagreement', 'warning'], ['agreement', 'source'],
  ['open question', 'uncertain'], ['analysis', 'neutral'],
  ['design choice', 'synthesis'], ['synthesis', 'synthesis'],
]);

function humanIdentity(value, fallback = '') {
  const text = String(value || '').trim();
  if (!text || /^(?:asset|source|chunk|canonical|job)_[a-z\d][\w-]*$/i.test(text) || /^(?=[\da-f]*[a-f])[\da-f]{8,}$/i.test(text) || /^[\da-f]{8}-[\da-f-]{27,}$/i.test(text)) return fallback;
  return text;
}

function evidenceIndex(snapshot = [], sourceInfo = []) {
  const sources = new Map(sourceInfo.filter(item => item?.id && item?.title).map(item => [item.id, item]));
  const assets = new Map();
  for (const group of snapshot) {
    const asset = group?.canonical_asset;
    if (!asset) continue;
    const evidence = group.evidence_trail || [];
    const entry = { title: asset.title || '', evidence };
    for (const id of [asset.id, ...(group.asset_ids || [])]) if (id) assets.set(id, entry);
  }
  function sourceFor(reference) {
    if (!reference) return null;
    const matches = [...sources.values()].filter(item => item.id === reference || item.id.startsWith(reference) || reference.startsWith(item.id) || item.id.split('_').at(-1)?.startsWith(reference));
    return matches.length === 1 ? matches[0] : null;
  }
  function evidenceForSource(source) {
    if (!source) return [];
    return [...assets.values()].flatMap(asset => asset.evidence.filter(item => item.source_id === source.id));
  }
  return {
    source(reference) {
      const source = sourceFor(reference);
      return { label: source ? [humanIdentity(source.title), humanIdentity(source.author)].filter(Boolean).join(' · ') || 'Source & evidence' : 'Source & evidence', evidence: evidenceForSource(source) };
    },
    asset(reference) {
      const asset = assets.get(reference);
      if (!asset) return { label: 'Source & evidence', evidence: [] };
      const sourceIds = [...new Set(asset.evidence.map(item => item.source_id).filter(Boolean))];
      const labels = sourceIds.map(sourceFor).filter(Boolean).map(source => [humanIdentity(source.title), humanIdentity(source.author)].filter(Boolean).join(' · ')).filter(Boolean);
      return { label: labels.length ? [...new Set(labels)].join(', ') : humanIdentity(asset.title, 'Source & evidence'), evidence: asset.evidence };
    },
    assetTitle(reference) { return humanIdentity(assets.get(reference)?.title, 'Knowledge used'); },
  };
}

function safeInlineText(text, references) {
  let clean = text;
  const markers = [];
  const addReference = (kind, id) => {
    const index = markers.push(references[kind](id)) - 1;
    return `\uE000${index}\uE001`;
  };
  clean = clean.replace(/\(?\s*Source:\s*([a-z\d][a-z\d_-]{1,}|[a-f\d]{8,})\s*\)?/gi, (_, id) => addReference(id.toLowerCase().startsWith('asset_') ? 'asset' : 'source', id));
  clean = clean.replace(/\basset_[a-z\d][\w-]*\b/gi, id => addReference('asset', id));
  clean = clean.replace(/\b(?:source|chunk|canonical|job|provider|attempt|request)(?:_[a-z]+)?_id\s*[:=]\s*[\w-]+/gi, () => addReference('source', ''));
  clean = clean.replace(/\b(?:chunk|canonical|source|job|provider|attempt|request)_[a-z\d][\w-]*\b/gi, () => addReference('source', ''));
  clean = clean.replace(/\b[\da-f]{8}-[\da-f-]{27,}\b/gi, () => addReference('source', ''));
  clean = clean.replace(/\b(?=[\da-f]*[a-f])[\da-f]{8,}\b/gi, id => addReference('source', id));
  // A short source reference is only treated as an identifier in citation syntax.
  return { clean, markers };
}

function appendInline(parent, raw, references, doc) {
  const { clean, markers } = safeInlineText(raw, references);
  const pattern = /(\uE000\d+\uE001|\*\*[^*]+\*\*|__[^_]+__|(?<!\*)\*[^*]+\*|(?<!_)_[^_]+_|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/)[^)]+\))/g;
  let cursor = 0;
  for (const match of clean.matchAll(pattern)) {
    if (match.index > cursor) parent.append(doc.createTextNode(clean.slice(cursor, match.index)));
    const token = match[0];
    const marker = /^\uE000(\d+)\uE001$/.exec(token);
    if (marker) appendEvidenceDisclosure(parent, markers[Number(marker[1])], doc, 'answer-citation');
    else if (token.startsWith('**') || token.startsWith('__')) {
      const node = doc.createElement('strong'); appendInline(node, token.slice(2, -2), references, doc); parent.append(node);
    } else if (token.startsWith('*') || token.startsWith('_')) {
      const node = doc.createElement('em'); appendInline(node, token.slice(1, -1), references, doc); parent.append(node);
    } else if (token.startsWith('`')) {
      const node = doc.createElement('code'); node.textContent = token.slice(1, -1); parent.append(node);
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/.exec(token);
      if (link) { const node = doc.createElement('a'); node.textContent = link[1]; node.href = link[2]; node.rel = 'noopener noreferrer'; node.target = '_blank'; parent.append(node); }
    }
    cursor = match.index + token.length;
  }
  if (cursor < clean.length) parent.append(doc.createTextNode(clean.slice(cursor)));
}

function appendEvidenceDisclosure(parent, item, doc, className = '') {
  const disclosure = doc.createElement('details');
  disclosure.className = `answer-evidence ${className}`.trim();
  const summary = doc.createElement('summary'); summary.textContent = item?.label || 'Source & evidence'; disclosure.append(summary);
  const evidence = item?.evidence || [];
  if (!evidence.length) {
    const note = doc.createElement('p'); note.textContent = 'Supporting evidence is available with the related knowledge.'; disclosure.append(note);
  } else {
    for (const entry of evidence) {
      const block = doc.createElement('blockquote');
      const context = [entry.chapter_or_section].filter(Boolean).join(' · ');
      if (context) { const label = doc.createElement('span'); label.className = 'answer-evidence-context'; label.textContent = context; block.append(label); }
      const quote = doc.createElement('p'); quote.textContent = entry.evidence || ''; block.append(quote); disclosure.append(block);
    }
  }
  parent.append(disclosure);
}

function isTableSeparator(line) {
  const cells = line.trim().replace(/^\||\|$/g, '').split('|');
  return cells.length > 1 && cells.every(cell => /^\s*:?-{3,}:?\s*$/.test(cell));
}
function tableCells(line) { return line.trim().replace(/^\||\|$/g, '').split(/(?<!\\)\|/).map(cell => cell.replace(/\\\|/g, '|').trim()); }
function isList(line) { return /^(\s*)([-*+] |\d+[.)] )(.+)$/.exec(line); }
function isBlockStart(lines, index) {
  const line = lines[index];
  return /^\s{0,3}(#{1,6})\s+/.test(line) || /^\s*>/.test(line) || /^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line) || isList(line) || (lines[index + 1] && isTableSeparator(lines[index + 1]));
}

function appendList(parent, lines, start, references, doc) {
  const first = isList(lines[start]);
  const root = doc.createElement(/^\d/.test(first[2]) ? 'ol' : 'ul');
  const stack = [{ indent: first[1].length, list: root, lastItem: null }];
  let index = start;
  while (index < lines.length) {
    const item = isList(lines[index]);
    if (!item) break;
    const indent = item[1].length;
    while (stack.length > 1 && indent < stack.at(-1).indent) stack.pop();
    let current = stack.at(-1);
    const ordered = /^\d/.test(item[2]);
    if (indent > current.indent && current.lastItem) {
      const nested = doc.createElement(ordered ? 'ol' : 'ul'); current.lastItem.append(nested);
      stack.push({ indent, list: nested, lastItem: null }); current = stack.at(-1);
    } else if (ordered !== (current.list.tagName?.toLowerCase() === 'ol') && indent === current.indent && current !== stack[0]) {
      stack.pop(); current = stack.at(-1);
      const sibling = doc.createElement(ordered ? 'ol' : 'ul'); current.lastItem?.append(sibling);
      stack.push({ indent, list: sibling, lastItem: null }); current = stack.at(-1);
    }
    const li = doc.createElement('li'); appendLabelledInline(li, item[3], references, doc); current.list.append(li); current.lastItem = li;
    index++;
  }
  parent.append(root); return index;
}

function appendLabelledInline(parent, text, references, doc) {
  const match = /^\s*\*\*(Source principle|Source tactic|Underlying mechanism|KE interpretation|Challenge \/ alternative|Applicability|Open question|Agreement|Disagreement|Analysis|Principle|Adaptation|Assumption|Experiment|Measurement|Warning|Design choice|Synthesis):\*\*\s*(.*)$/i.exec(text);
  if (!match) return appendInline(parent, text, references, doc);
  const label = doc.createElement('span'); label.className = `answer-label answer-label-${LABEL_KIND.get(match[1].toLowerCase()) || 'neutral'}`; label.textContent = match[1]; parent.append(label);
  if (match[2]) { parent.append(doc.createTextNode(' ')); appendInline(parent, match[2], references, doc); }
}

export function renderGroundedAnswer(text, { document: doc = globalThis.document, snapshot = [], sourceInfo = [] } = {}) {
  const root = doc.createElement('article'); root.className = 'answer-document';
  const references = evidenceIndex(snapshot, sourceInfo);
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) { index++; continue; }
    const heading = /^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/.exec(lines[index]);
    if (heading) { const tag = `h${Math.min(6, heading[1].length + 1)}`; const node = doc.createElement(tag); appendInline(node, heading[2], references, doc); root.append(node); index++; continue; }
    if (index + 1 < lines.length && isTableSeparator(lines[index + 1]) && lines[index].includes('|')) {
      const table = doc.createElement('table'), wrapper = doc.createElement('div'), viewport = doc.createElement('div'); wrapper.className = 'answer-table-scroll'; viewport.className = 'answer-table-viewport';
      const thead = doc.createElement('thead'), header = doc.createElement('tr');
      for (const cell of tableCells(lines[index])) { const th = doc.createElement('th'); appendInline(th, cell, references, doc); header.append(th); }
      thead.append(header); table.append(thead); const tbody = doc.createElement('tbody'); index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) { const tr = doc.createElement('tr'); for (const cell of tableCells(lines[index])) { const td = doc.createElement('td'); appendInline(td, cell, references, doc); tr.append(td); } tbody.append(tr); index++; }
      table.append(tbody); viewport.append(table); wrapper.append(viewport);
      const hint = doc.createElement('span'); hint.className = 'answer-table-scroll-hint'; hint.textContent = 'Scroll sideways to see the full table'; hint.setAttribute('aria-hidden', 'true'); wrapper.append(hint);
      root.append(wrapper); continue;
    }
    if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(lines[index])) { root.append(doc.createElement('hr')); index++; continue; }
    if (/^\s*>/.test(lines[index])) {
      const quote = doc.createElement('blockquote'), content = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) content.push(lines[index++].replace(/^\s*>\s?/, ''));
      const paragraph = doc.createElement('p'); appendInline(paragraph, content.join(' '), references, doc); quote.append(paragraph); root.append(quote); continue;
    }
    if (isList(lines[index])) { index = appendList(root, lines, index, references, doc); continue; }
    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) paragraph.push(lines[index++].trim());
    if (!paragraph.length) { paragraph.push(lines[index++]); }
    const node = doc.createElement('p');
    const first = /^\*\*(Source principle|Source tactic|Underlying mechanism|KE interpretation|Challenge \/ alternative|Applicability|Open question|Agreement|Disagreement|Analysis|Principle|Adaptation|Assumption|Experiment|Measurement|Warning|Design choice|Synthesis):\*\*\s*(.*)$/i.exec(paragraph[0]);
    if (first) {
      const label = doc.createElement('span'); label.className = `answer-label answer-label-${LABEL_KIND.get(first[1].toLowerCase()) || 'neutral'}`; label.textContent = first[1]; node.append(label);
      const rest = [first[2], ...paragraph.slice(1)].filter(Boolean).join(' '); if (rest) { node.append(doc.createTextNode(' ')); appendInline(node, rest, references, doc); }
    } else appendInline(node, paragraph.join(' '), references, doc);
    root.append(node);
  }
  return root;
}

export function renderGroundedInline(text, { document: doc = globalThis.document, snapshot = [], sourceInfo = [] } = {}) {
  const node = doc.createElement('span');
  appendInline(node, String(text || ''), evidenceIndex(snapshot, sourceInfo), doc);
  return node;
}

export function createAnswerEvidenceIndex(snapshot = [], sourceInfo = []) { return evidenceIndex(snapshot, sourceInfo); }

export function observeAnswerTableOverflow(root) {
  const refresh = () => {
    for (const wrapper of root.querySelectorAll('.answer-table-scroll')) {
      const viewport = wrapper.querySelector('.answer-table-viewport');
      const overflowing = !!viewport && viewport.scrollWidth > viewport.clientWidth + 1;
      wrapper.classList.toggle('is-overflowing', overflowing);
      if (overflowing) {
        viewport.tabIndex = 0;
        viewport.setAttribute('role', 'region');
        viewport.setAttribute('aria-label', 'Scrollable table. Scroll horizontally to see all columns.');
      } else {
        viewport?.removeAttribute('tabindex');
        viewport?.removeAttribute('role');
        viewport?.removeAttribute('aria-label');
      }
    }
  };
  refresh();
  if (typeof ResizeObserver === 'undefined') return null;
  const observer = new ResizeObserver(refresh);
  observer.observe(root);
  for (const viewport of root.querySelectorAll('.answer-table-viewport')) observer.observe(viewport);
  return observer;
}
