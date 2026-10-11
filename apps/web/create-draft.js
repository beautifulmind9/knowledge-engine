// Draft text stays in this tab's memory; it is never placed in the URL or storage.
export function captureCreateFields(form, previous = []) {
  const values = new Map(previous);
  for (const [name, value] of new FormData(form)) {
    if (!['Library scope', 'Materials — optional; use Ctrl / Command to select several'].includes(name)) values.set(name, value);
  }
  return [...values];
}
export function restoreCreateFields(form, names) {
  for (const [name, value] of form.createDraftValues || []) {
    if (names && !names.includes(name)) continue;
    const input = form.elements.namedItem(name);
    if (input) input.value = value;
  }
}
