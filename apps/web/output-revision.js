const lf = value => value.replace(/\r\n?/g, '\n');

export function revisionPayload(fd, parent) {
  const body = {instruction: fd.get('instruction')};
  if (fd.get('manual') !== 'on') return body;

  const content = lf(fd.get('content'));
  const choices = lf(fd.get('choices'));
  body.title = fd.get('title');
  // Textarea/FormData serialization can change line endings without an edit.
  // Restore untouched stored values exactly, including legacy line endings.
  body.content = content === lf(parent.content) ? parent.content : content;
  body.design_choices = choices === lf(parent.design_choices.join('\n'))
    ? [...parent.design_choices]
    : choices.split('\n').filter(Boolean);
  return body;
}
