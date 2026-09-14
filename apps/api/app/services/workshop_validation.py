"""Conservative, local checks for explicitly timed workshop plans.

This is not a semantic verifier. Unsupported or ambiguous prose is reported as
needs_review, never silently interpreted as a valid schedule.
"""
import re

NUMBER = r'\d+(?:\.\d+)?'
MINUTES = r'(?:minutes?|mins?)\b'
DURATION = re.compile(rf'(?P<n>{NUMBER})\s*[- ]?\s*(?P<unit>hours?|hrs?|minutes?|mins?)\b', re.I)
RANGE = re.compile(r'(?<![\d:])(?P<a>\d{1,3}(?::\d{2})?)\s*[-–—]\s*(?P<b>\d{1,3}(?::\d{2})?)(?:\s*(?:minutes?|mins?))?(?![\d:])', re.I)
FORMAT_RULE = re.compile(rf'\b(?:switch|change|vary|alternate)\b[^.!?\n]{{0,100}}?\b(?:teaching\s+)?formats?\b[^.!?\n]{{0,45}}?\b(?:every|at most|no more than)\s+({NUMBER})\s*{MINUTES}', re.I)
STOP_SECTIONS = {'activities','activity details','facilitator notes','breaks','learning goals','materials','design choices','applied knowledge','checks','completion checks','review questions','notes'}


def _minutes(match):
    return float(match['n']) * (60 if match['unit'].lower().startswith(('hour','hr')) else 1)


def _label(value):
    value = re.sub(r'^\s*(?:\d+[.)]\s*|[-*]\s+)', '', value)
    value = re.sub(r'[^a-z0-9 ]', ' ', value.lower())
    return ' '.join(value.split())


def _time(value):
    if ':' in value:
        hour, minute = value.split(':')
        return int(hour) * 60 + int(minute)
    return int(value)


def _heading(line):
    return line.strip().strip('#* :').lower()


def requested_minutes(brief):
    """Accept explicitly stated total duration; don't mistake activity lengths for it."""
    values = []
    constraints = brief.get('constraints', [])
    texts = constraints + [brief.get('situation', ''), brief.get('goal', '')]
    for text in texts:
        # Separate requirements so "3 hours total; breaks of 10 minutes" stays 180.
        for clause in re.split(r'[;\n]|\.(?!\d)', text):
            matches = list(DURATION.finditer(clause))
            if not matches:
                continue
            bare = re.fullmatch(r'\s*' + DURATION.pattern + r'\s*', clause, re.I)
            explicit = bare or re.search(r'\b(total|duration|long|workshop|session)\b', clause, re.I)
            if not explicit:
                continue
            if re.search(r'\b(break|practice|activity|exercise)\b', clause, re.I) and not re.search(r'\b(total|duration)\b', clause, re.I):
                continue
            if len(matches) == 1:
                # Ranges, bounds, approximations, and clock times aren't exact totals.
                if re.search(r'\d\s*[-–—]\s*\d|\b(about|around|up to|at least|maximum|minimum|roughly)\b|\d:\d', clause, re.I):
                    continue
                values.append(_minutes(matches[0]))
            elif len(matches) == 2 and matches[0]['unit'].lower().startswith(('hour','hr')) and matches[1]['unit'].lower().startswith('min'):
                between = clause[matches[0].end():matches[1].start()].strip()
                if between in ('', 'and'):
                    values.append(sum(_minutes(m) for m in matches))
    unique = sorted(set(values))
    return (unique[0] if len(unique) == 1 and unique[0] > 0 else None), unique


def _block(line, number):
    clean = re.sub(r'[*#`]', '', line).strip().strip('|').strip()
    if re.search(r'\b(about|roughly|approximately|around|up to|optional|alternative)\b', clean, re.I):
        return None
    if re.match(r'^(?:total|time\s*\||duration\s*\|)', clean, re.I):
        return None
    time_range = RANGE.search(clean)
    durations = list(DURATION.finditer(clean))
    if time_range:
        # An explicit unit after a numeric range refers to its endpoint, not duration.
        if re.search(r'\b(?:am|pm|hours?|hrs?)\b', clean, re.I):
            return None
        start, end = _time(time_range['a']), _time(time_range['b'])
        label = clean[:time_range.start()] + ' ' + clean[time_range.end():]
        label = DURATION.sub('', label).strip(' |:—–-()')
        if not label:
            return None
        declared = [_minutes(m) for m in durations if m.start() >= time_range.end()]
        return {'label': label, 'duration_minutes': end-start, 'start_minute': start,
                'end_minute': end, 'line_number': number, 'text': line, 'declared_durations': declared,
                'malformed_time': any(':' in value and int(value.split(':')[1]) >= 60
                                      for value in (time_range['a'], time_range['b']))}
    if len(durations) == 1:
        match = durations[0]
        label = (clean[:match.start()] + ' ' + clean[match.end():]).strip(' |:—–-()')
        if label:
            return {'label': label, 'duration_minutes': _minutes(match), 'start_minute': None,
                    'end_minute': None, 'line_number': number, 'text': line, 'declared_durations': []}
    return None


def _practice_timings(line):
    """Extract explicit practice/role-play durations, without inferring identity."""
    clean = re.sub(r'[*`]', '', line)
    activity = r'(?:practice|role[- ]play)'
    patterns = [
        rf'(?P<n>{NUMBER})\s*[- ]?\s*(?P<unit>{MINUTES})\s+(?:of\s+)?(?P<activity>{activity})\b',
        rf'\b(?P<activity>{activity})\s*(?:\(\s*|:\s*|for\s+)(?P<n>{NUMBER})\s*(?P<unit>{MINUTES})',
    ]
    results = []
    for pattern in patterns:
        for match in re.finditer(pattern, clean, re.I):
            item = {'label': match['activity'].lower(), 'duration_minutes': _minutes(match)}
            if item not in results:
                results.append(item)
    return results


def validate_workshop(output, brief, knowledge_snapshot):
    checks, issues = [], []
    def issue(code, severity, message, **evidence):
        issues.append({'code': code, 'severity': severity, 'message': message, **evidence})
    target, candidates = requested_minutes(brief)
    if target is None:
        issue('requested_duration_unknown', 'review', 'The brief has no single supported exact total duration.', candidates=candidates)
    lines = output['content'].splitlines()
    inside, found = False, False
    blocks, agenda_lines, declared_totals = [], set(), []
    # Preserve indentation: nested notes belong to their parent block.
    agenda_indent = None
    for index, line in enumerate(lines, 1):
        heading = _heading(line)
        if re.match(r'^(?:timed\s+)?agenda(?:\s*\(.*\))?$', heading):
            inside, found = True, True
            agenda_indent = None
            continue
        if inside and (heading in STOP_SECTIONS or re.match(r'^\s{0,3}#{1,6}\s+', line)):
            inside = False
        if not inside or not line.strip():
            continue
        agenda_lines.add(index)
        indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
        if agenda_indent is None:
            agenda_indent = indent
        if indent > agenda_indent:
            continue
        agenda_indent = min(agenda_indent, indent)
        if re.match(r'^[\s|:\-]+$', line) or re.match(r'^\s*\|?\s*(?:time|duration)\s*\|', line, re.I):
            continue
        if re.match(r'^\s*[*| ]*total\b', line, re.I):
            durations = list(DURATION.finditer(line))
            if len(durations) == 1:
                declared_totals.append(_minutes(durations[0]))
            else:
                issue('declared_total_unknown', 'review', 'The stated agenda total could not be checked.', line_number=index)
            continue
        block = _block(line, index)
        if block:
            blocks.append(block)
        else:
            issue('unparsed_agenda_line', 'review', 'An agenda line could not be checked; totals may be incomplete.', line_number=index, text=line)
    if not found or not blocks:
        issue('agenda_unparsed', 'review', 'No supported timed Agenda section was found. Use one row per block with elapsed minute ranges.')
    total = sum(b['duration_minutes'] for b in blocks) if blocks else None
    incomplete = any(i['code'] == 'unparsed_agenda_line' for i in issues)
    provisional = incomplete or any(b.get('malformed_time') for b in blocks)
    checks.append({'criterion':'agenda_total', 'status': 'unknown' if target is None or total is None or provisional else ('passed' if abs(total-target)<.01 else 'failed'),
                   'requested_minutes':target, 'calculated_minutes':total})
    if not provisional and target is not None and total is not None and abs(total-target) >= .01:
        issue('agenda_total_mismatch', 'error', f'Agenda blocks total {total:g} minutes; the brief requests {target:g}.')
    if not provisional and total is not None and any(abs(value-total) >= .01 for value in declared_totals):
        issue('declared_total_mismatch', 'error', 'The agenda’s stated total disagrees with the sum of its blocks.', declared_minutes=declared_totals, calculated_minutes=total)
    for block in blocks:
        if block.get('malformed_time'):
            issue('malformed_elapsed_time', 'review',
                  'A timestamp has a minute component of 60 or more. The displayed duration is provisional, interpreting it as elapsed minutes; rewrite using minute ranges or valid HH:MM notation.',
                  line_number=block['line_number'], text=block['text'])
        if block['duration_minutes'] <= 0:
            issue('nonpositive_block', 'error', 'An agenda block ends before it starts or has zero duration.', line_number=block['line_number'])
        declared = block['declared_durations']
        if len(declared) > 1:
            # Multiple timings may describe components, or a total plus components.
            parts = list(declared)
            if len(parts) > 2 and abs(parts[0]-block['duration_minutes']) < .01:
                parts = parts[1:]
            if abs(sum(parts)-block['duration_minutes']) >= .01:
                issue('block_components_need_review', 'review',
                      'Multiple durations do not reconcile as a complete block breakdown. Clarify components, repeats, or alternatives.',
                      line_number=block['line_number'], component_minutes=parts, block_minutes=block['duration_minutes'])
        elif any(abs(d-block['duration_minutes']) >= .01 for d in declared):
            issue('block_duration_conflict', 'error', 'The stated block duration disagrees with its time range.', line_number=block['line_number'])
    ranged = [b for b in blocks if b['start_minute'] is not None]
    if ranged and len(ranged) != len(blocks):
        issue('mixed_agenda_timing', 'review', 'Mixed ranges and durations prevent a complete gap/overlap check.')
    if ranged and len(ranged) == len(blocks):
        for left, right in zip(ranged, ranged[1:]):
            delta = right['start_minute']-left['end_minute']
            if delta:
                issue('agenda_gap' if delta > 0 else 'agenda_overlap', 'error', f'Agenda contains a {abs(delta):g}-minute {"gap" if delta>0 else "overlap"}.', line_number=right['line_number'])
    # Compare separately stated, identically named activity timings. Different
    # labels/subactivities and suggested alternatives are deliberately not equated.
    for index, line in enumerate(lines, 1):
        if index in agenda_lines or re.search(r'\b(optional|alternative|for example|could|instead)\b', line, re.I):
            continue
        detail = _block(line, index)
        if not detail:
            continue
        matches = [b for b in blocks if _label(b['label']) == _label(detail['label'])]
        if len(matches) == 1 and abs(matches[0]['duration_minutes']-detail['duration_minutes']) >= .01:
            issue('activity_duration_conflict', 'error', f'{matches[0]["label"]} has inconsistent agenda and activity-detail timings.',
                  line_number=index, agenda_minutes=matches[0]['duration_minutes'], detail_minutes=detail['duration_minutes'])
    # Practice and role-play can refer to the same task, but also to a parent
    # and subtask. Surface differing timings as review evidence, never proof.
    agenda_practice = []
    for index in sorted(agenda_lines):
        for item in _practice_timings(lines[index-1]):
            agenda_practice.append({**item, 'line_number': index})
    for index, line in enumerate(lines, 1):
        if index in agenda_lines or re.search(r'\b(optional|alternative|for example|could|instead)\b', line, re.I):
            continue
        for detail in _practice_timings(line):
            if len(agenda_practice) == 1:
                candidate = agenda_practice[0]
                if abs(candidate['duration_minutes']-detail['duration_minutes']) >= .01:
                    issue('practice_duration_needs_review', 'review',
                          'Agenda practice timing differs from a later practice/role-play detail. Confirm whether these describe the same task or a separately timed subtask.',
                          line_number=index, agenda_line_number=candidate['line_number'],
                          agenda_minutes=candidate['duration_minutes'], detail_minutes=detail['duration_minutes'])
            elif agenda_practice and any(abs(c['duration_minutes']-detail['duration_minutes']) >= .01 for c in agenda_practice):
                issue('practice_identity_unknown', 'review',
                      'Multiple agenda practice timings could match this detail. Use explicit task labels to reconcile durations.',
                      line_number=index, candidates=agenda_practice, detail_minutes=detail['duration_minutes'])
    rules = []
    for group in knowledge_snapshot:
        asset = group['canonical_asset']
        evidence = '\n'.join(str(asset.get(k) or '') for k in ('what_it_says','evidence','condition','action'))
        for match in FORMAT_RULE.finditer(evidence):
            rule = {'asset_id':asset['id'], 'maximum_minutes':float(match[1]), 'text':match[0]}
            if rule not in rules and rule['maximum_minutes'] > 0:
                rules.append(rule)
    for rule in rules:
        for block in blocks:
            if re.search(r'\b(break|lunch|rest)\b', block['label'], re.I):
                continue
            if block['duration_minutes'] > rule['maximum_minutes']:
                issue('format_switch_needs_review', 'review',
                      f'{block["label"]} runs {block["duration_minutes"]:g} minutes; retrieved guidance calls for a format change every {rule["maximum_minutes"]:g}. Show separately timed format changes or explain why the rule does not apply.',
                      asset_id=rule['asset_id'], rule_text=rule['text'], line_number=block['line_number'])
    # Flags remain even if design_choices or usage notes claim compliance.
    status = 'failed' if any(i['severity']=='error' for i in issues) else ('needs_review' if issues else 'checks_passed')
    return {'validation_status':status, 'timing_checks':checks, 'issues':issues, 'agenda_blocks':blocks,
            'numeric_rules_checked':rules, 'scope':'Supported explicit timings and format-switch rules only; not semantic or pedagogical approval.'}
