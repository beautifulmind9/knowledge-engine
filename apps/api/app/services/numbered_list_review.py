"""Deterministic review hints, never semantic completion or source repair.

Only explicit count nouns and sequential Arabic numbered lists are supported.
Signals deliberately live outside the strict KnowledgeAsset schema and never
reject settlement. Noun matching cannot establish list identity; partial titles
cannot establish body scope. Runs may merge across headings, omit singletons,
and miss empty fields. Evidence may be a legitimate shortened quotation.
These lexical hints are not proof of source or generated-claim completeness.
"""
import re

_WORDS = dict(zip('two three four five six seven eight nine ten'.split(), range(2, 11)))
_DECLARED = re.compile(r'\b(\d{1,2}|' + '|'.join(_WORDS) + r')\s+(?:primary\s+)?(motivations|steps|components|parts|reasons|principles|examples)\b', re.I)
_MARKER = re.compile(r'(?<!\S)(\d{1,2})[.)]\s+(?=\S)')
# Require an explicit scope disclaimer, never a topic adjective.
_PARTIAL = re.compile(
    r'^(?:partial|incomplete)\s+(?:list|excerpt|subset|interpretation)\b'
    r'|^(?:excerpt|subset)\s+of\b'
    r'|\((?:partial|incomplete)(?:\s+list)?\)\s*$', re.I)


def declarations(text):
    return [(int(m.group(1)) if m.group(1).isdigit() else _WORDS[m.group(1).lower()],
             m.group(2).lower(), m.start(), m.end())
            for m in _DECLARED.finditer(text or '')]


def scoped_runs(text):
    """Keep each run's local heading; never pool declarations across lists."""
    runs = []
    for marker in _MARKER.finditer(text or ''):
        n = int(marker.group(1))
        if runs and n == runs[-1][0][-1] + 1:
            runs[-1][0].append(n)
        else:
            runs.append(([n], marker.start(), marker.end()))
    result = []
    previous_end = 0
    for numbers, start, end in runs:
        local = declarations(text[previous_end:start])
        # Only a declaration immediately introducing this list is reliable.
        heading = local[-1] if local and not text[previous_end + local[-1][3]:start].strip(' :.\n\t-') else None
        result.append((numbers, heading, start))
        previous_end = end
    return [(r, h, start) for r, h, start in result if len(r) >= 2]



def review_asset(asset):
    value = asset.model_dump() if hasattr(asset, 'model_dump') else asset
    claim = ' '.join(value.get(k) or '' for k in ('title', 'what_it_says'))
    claims = declarations(claim)
    partial = bool(_PARTIAL.search(value.get('title', '')))
    signals = []
    for field in ('components', 'steps'):
        nouns = {'steps'} if field == 'steps' else {'components', 'parts', 'motivations', 'reasons', 'principles'}
        counts = {count for count, noun, _, _ in claims if noun in nouns}
        members = value.get(field) or []
        if members and len(counts) == 1 and len(members) != next(iter(counts)) and not partial:
            signals.append(dict(reason='declared_count_mismatch', field=field,
                                declared_counts=sorted(counts), observed_count=len(members)))
        elif members and len(counts) > 1:
            signals.append(dict(reason='ambiguous_list_association', field=field,
                                declared_counts=sorted(counts), observed_count=len(members)))
    evidence = value.get('evidence', '')
    runs = scoped_runs(evidence)
    for run, heading, start in runs:
        # A bare single run may correspond to a single claim. Otherwise require
        # its own explicit heading; supporting examples are independent lists.
        counts = {heading[0]} if heading else set()
        if not heading and len(runs) == 1 and len({(c, n) for c, n, _, _ in claims}) == 1 and not evidence[:start].strip():
            counts = {claims[0][0]}
        if run[0] == 1 and counts and run[-1] < min(counts):
            signals.append(dict(reason='partial_numbered_evidence' if partial else 'incomplete_numbered_evidence',
                                field='evidence', declared_counts=sorted(counts), observed_count=run[-1]))
        elif run[0] == 1 and not counts and claims:
            signals.append(dict(reason='ambiguous_list_association', field='evidence',
                                declared_counts=sorted({c for c, _, _, _ in claims}), observed_count=run[-1]))
    return signals


def review_chunk_pair(current, following=None):
    """Caller supplies ordered chunks. Never bridge sources, gaps or unknown order.

    Overlap is allowed: the next window can repeat 1..N before supplying N+1.
    These are review hints only; they do not establish matching list semantics.
    """
    text = current.get('text', '')
    runs = [(r, heading) for r, heading, _ in scoped_runs(text)
            if r[0] == 1 and heading and r[-1] < heading[0]]
    if not runs:
        return []
    run, heading = runs[-1]
    counts = {heading[0]}
    # The list must reach the actual tail, rather than being a shorter list
    # elsewhere in a chunk that happens to contain a count declaration.
    tail = list(_MARKER.finditer(text))[-1]
    if int(tail.group(1)) != run[-1] or len(text[tail.end():].split()) > 80:
        return []
    signal = dict(reason='unfinished_numbered_list', source_id=current.get('source_id'),
                  chunk_id=current.get('id'), observed_count=run[-1], declared_counts=sorted(counts))
    if (following and current.get('source_id') and current.get('source_id') == following.get('source_id')
            and isinstance(current.get('chunk_index'), int)
            and following.get('chunk_index') == current['chunk_index'] + 1):
        next_numbers = {int(m.group(1)) for m in _MARKER.finditer(following.get('text', ''))}
        if run[-1] + 1 in next_numbers:
            signal.update(reason='possible_adjacent_list_continuation', next_chunk_id=following.get('id'))
    return [signal]
