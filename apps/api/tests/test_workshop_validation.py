"""Original regressions reproducing the reported timing failure pattern; no AI calls."""
import json
from types import SimpleNamespace
import pytest
from app.services.output_modes import quality_report
from app.services.workshop_validation import requested_minutes


def plan(content):
    return {'title':'Practice session','output_type':'workshop_plan','content':content,
            'applied_knowledge':[{'asset_id':'rule','usage_note':'Follows the 20-minute format-switch rule.'}],
            'design_choices':['The 40-minute block complies with the format-switch rule.']}


def source_rule(text='Switch Teaching Format every 20 minutes.'):
    return [{'canonical_asset':{'id':'rule','what_it_says':text,'evidence':text}}]


def review(content, total='60 minutes total', rules=None):
    return quality_report(plan(content),{'constraints':[total]},source_rule() if rules is None else rules)


def codes(report):
    return {i['code'] for i in report['issues']}


def test_reported_40_minute_block_and_5_10_minute_practice():
    report=review('''Agenda
| Time | Activity |
| --- | --- |
| 0–10 min | Welcome |
| 10–50 min | Guided Practice |
| 50–55 min | Break |
| 55–65 min | Practice |
Activities
Practice (5 minutes)
Guided Practice follows the 20-minute format-switch rule.
''','65 minutes total')
    assert all(c['passed'] for c in report['structure_checks'])
    assert report['validation_status']=='failed'
    assert {'activity_duration_conflict','format_switch_needs_review'} <= codes(report)
    flag=next(i for i in report['issues'] if i['code']=='format_switch_needs_review')
    assert flag['asset_id']=='rule' and '40 minutes' in flag['message']


def test_valid_180_minute_schedule_with_explicit_format_changes():
    labels=['Welcome','Demonstration','Pair exercise','Break','Discussion','Individual exercise','Break','Peer review','Reflection']
    content='## Agenda\n| Time | Activity |\n|---|---|\n'+'\n'.join(f'| {i*20}–{(i+1)*20} min | {label} |' for i,label in enumerate(labels))+'\n## Activities\nPair exercise (20 minutes)'
    report=review(content,'3 hours total')
    assert report['validation_status']=='checks_passed',report
    assert report['timing_checks'][0]['calculated_minutes']==180
    assert report['human_review_required']


@pytest.mark.parametrize('text,code',[
    ('0–20 min | Welcome\n20–50 min | Practice','agenda_total_mismatch'),
    ('0–30 min | Welcome\n40–70 min | Practice','agenda_gap'),
    ('0–30 min | Welcome\n20–50 min | Practice','agenda_overlap'),
    ('0–30 min | Welcome\n30–20 min | Practice','nonpositive_block'),
    ('0–10 min | Practice (5 minutes)\n10–60 min | Reflection','block_duration_conflict'),
])
def test_definite_schedule_errors(text,code):
    report=review('Agenda\n'+text,rules=[])
    assert code in codes(report)
    assert report['validation_status']=='failed'


@pytest.mark.parametrize('content',[
    'Agenda\nWelcome, practice, a break and reflection.\nActivities',
    'Agenda\nAbout 20 minutes of discussion\nActivities',
    'Agenda\n09:00 AM–10:00 AM | Practice\nActivities',
    'We will meet and practice together for 60 minutes.',
])
def test_unsupported_or_incomplete_prose_cannot_pass(content):
    assert review(content)['validation_status']!='checks_passed'


@pytest.mark.parametrize('text,expected',[
    ('3 hours total',180),('90 minutes total',90),('1 hour and 30 minutes total',90),
    ('I need a 3-hour workshop',180),('60 minutes',60),
    ('3 hours total; breaks of 10 minutes',180),
    ('Breaks of 10 minutes',None),('Practice for 20 minutes',None),
    ('2–3 hours total',None),('About 3 hours total',None),('up to 3 hours total',None),
])
def test_requested_duration_is_not_an_activity_length(text,expected):
    assert requested_minutes({'constraints':[text]})[0]==expected


def test_conflicting_brief_totals_require_review():
    output=plan('Agenda\n0–60 min | Practice')
    report=quality_report(output,{'constraints':['60 minutes total','90 minutes total']},[])
    assert report['validation_status']=='needs_review'
    assert 'requested_duration_unknown' in codes(report)


def test_clock_ranges_and_breaks_count_toward_total():
    report=review('Agenda\n09:00–09:20 | Welcome\n09:20–09:40 | Practice\n09:40–10:00 | Break')
    assert report['validation_status']=='checks_passed'
    assert report['timing_checks'][0]['calculated_minutes']==60


def test_break_is_not_a_teaching_format_violation():
    report=review('Agenda\n0–20 min | Practice\n20–60 min | Lunch break')
    assert report['validation_status']=='checks_passed'


def test_explicit_subactivity_does_not_conflict_with_parent_block():
    report=review('Agenda\n0–40 min | Guided Practice\n40–60 min | Break\nActivities\nPair exercise (5 minutes)')
    assert 'activity_duration_conflict' not in codes(report)
    assert 'format_switch_needs_review' in codes(report)
    assert report['validation_status']=='needs_review'


def test_unrelated_numeric_source_does_not_become_a_format_rule():
    report=review('Agenda\n0–60 min | Practice',rules=source_rule('Take a 20-minute break after the session.'))
    assert not report['numeric_rules_checked']
    assert 'format_switch_needs_review' not in codes(report)


def test_manual_revision_rechecks_without_changing_old_version(client,knowledge,monkeypatch):
    from app.services import ai_gateway
    def no_calls(*args,**kwargs):
        raise AssertionError('Manual validation must not call Gemini')
    monkeypatch.setattr(ai_gateway,'generate',no_calls)
    generated=plan('Agenda\n0–40 min | Guided Practice\n40–60 min | Break\nActivities\nGuided Practice (5 minutes)')
    generated['applied_knowledge'][0]['asset_id']=knowledge['id']
    brief={'situation':'A practice workshop','goal':'Practice breaks for learning','constraints':['60 minutes total'],
           'source_ids':[knowledge['source_id']],'output_type':'workshop_plan'}
    response=client.post('/outputs',json={'brief':brief,'output':generated})
    assert response.status_code==200,response.text
    old=response.json()
    assert old['generation_metadata']['quality']['validation_status']=='failed'
    new=client.post(f"/outputs/{old['id']}/revise",json={'instruction':'Fix inconsistent duration',
        'content':'Agenda\n0–20 min | Guided Practice\n20–40 min | Discussion\n40–60 min | Break\nActivities\nGuided Practice (20 minutes)'}).json()
    assert new['generation_metadata']['quality']['validation_status']=='checks_passed'
    assert client.get(f"/outputs/{old['id']}").json()==old
    assert client.get(f"/outputs/{old['id']}/quality").json()['validation_status']=='failed'
    assert 'Quality review' in client.get(f"/outputs/{old['id']}/export").text


@pytest.mark.parametrize('save',[True,False])
def test_generation_exposes_review_even_without_saving(client,knowledge,monkeypatch,save):
    from app.services import ai_gateway
    generated=plan('Agenda\n0–40 min | Practice\nActivities\nPractice (5 minutes)')
    generated['applied_knowledge'][0]['asset_id']=knowledge['id']
    calls=[]
    def fake(*args):
        calls.append(args)
        return SimpleNamespace(output_text=json.dumps(generated))
    monkeypatch.setattr(ai_gateway,'generate',fake)
    response=client.post('/workshops/generate',json={'situation':'A practice workshop','goal':'Practice breaks for learning',
        'source_ids':[knowledge['source_id']],'constraints':['60 minutes total'],'output_type':'workshop_plan','save':save})
    assert response.status_code==200,response.text
    assert response.json()['quality_report']['validation_status']=='failed'
    assert len(calls)==1  # no automatic repair attempt
    assert ('saved_output' in response.json()) is save


def test_approximate_block_cannot_contribute_to_a_verified_total():
    report=review('Agenda\nAbout 20 minutes | Discussion\n40 minutes | Practice',rules=[])
    assert report['validation_status']!='checks_passed'
    assert 'unparsed_agenda_line' in codes(report)


def test_stated_agenda_total_must_match_its_blocks():
    report=review('Agenda\n0–20 min | Demonstration\n20–40 min | Practice\n40–60 min | Break\nTotal: 50 minutes')
    assert report['validation_status']=='failed'
    assert 'declared_total_mismatch' in codes(report)


@pytest.mark.parametrize('boundary',[
    '# Activities & Completion Checks', '## Activities & Completion Checks',
    '### Activities & Completion Checks', '#### Practice (5 minutes)',
    '##### Task Time Limit', '###### Follow-up',
])
def test_reported_90_minute_agenda_does_not_become_185(boundary):
    # Reconstruction of the screenshot's failure pattern, not the private output.
    report = review('''## Agenda
- 0:00–0:15 | Welcome
- 0:15–0:35 | Demonstration
- 0:35–0:75 | Guided Practice
  - At the 85-minute mark, remind participants to wrap up.
- 0:75–0:85 | Break
- 0:85–0:90 | Reflection
''' + boundary + '''
5-minute role-play
Task Time Limit: 5 minutes
''', '90 minutes total')
    assert len(report['agenda_blocks']) == 5
    assert report['timing_checks'][0]['calculated_minutes'] == 90
    assert report['timing_checks'][0]['status'] == 'unknown'
    assert 'agenda_total_mismatch' not in codes(report)
    assert 'malformed_elapsed_time' in codes(report)
    assert report['validation_status'] == 'needs_review'
    assert any(i['code'] == 'format_switch_needs_review' and '40 minutes' in i['message']
               for i in report['issues'])


@pytest.mark.parametrize('prefix,nested', [('- ', '  - '), ('1. ', '   - '), ('', '    '), ('  - ', '    - ')])
def test_nested_notes_and_ranges_do_not_add_agenda_blocks(prefix, nested):
    content = ('## Agenda\n' + prefix + '0–20 min | Welcome\n'
               + nested + '10–15 min | Short exercise\n'
               + nested + 'Reminder at the 85-minute mark\n'
               + prefix + '20–40 min | Practice\n'
               + prefix + '40–60 min | Break\n### Activities & Completion Checks\n'
               + '5-minute role-play')
    report = review(content)
    assert report['validation_status'] == 'checks_passed', report
    assert len(report['agenda_blocks']) == 3
    assert report['timing_checks'][0]['calculated_minutes'] == 60


def test_valid_clock_notation_is_not_flagged_as_malformed():
    report = review('Agenda\n0:00–0:20 | Welcome\n0:20–0:40 | Practice\n0:40–1:00 | Break')
    assert report['validation_status'] == 'checks_passed'
    assert 'malformed_elapsed_time' not in codes(report)


@pytest.mark.parametrize('parts', ['10 minutes demonstration + 5 minutes practice + 15 minutes discussion',
                                  '30 minutes total: 10 minutes demonstration + 5 minutes practice + 15 minutes discussion'])
def test_parent_duration_is_not_compared_to_each_component(parts):
    report = review('Agenda\n0–30 min | Learning cycle: ' + parts, '30 minutes total', rules=[])
    assert report['validation_status'] == 'checks_passed', report


def test_unreconciled_components_require_review():
    report = review('Agenda\n0–30 min | Cycle: 10 minutes demonstration + 5 minutes practice + 10 minutes discussion',
                    '30 minutes total', rules=[])
    assert 'block_components_need_review' in codes(report)
    assert 'block_duration_conflict' not in codes(report)


@pytest.mark.parametrize('practice', ['10 minutes of practice', '10-minute practice', 'Practice (10 minutes)'])
def test_cross_section_practice_roleplay_difference_requires_review(practice):
    report = review('Agenda\n0–40 min | Guided Practice\n  - Cycle: ' + practice +
                    '\n40–60 min | Break\n### Activities & Completion Checks\nUse a 5-minute role-play.')
    assert 'practice_duration_needs_review' in codes(report)
    assert 'format_switch_needs_review' in codes(report)
    assert report['timing_checks'][0]['calculated_minutes'] == 60
    flag = next(i for i in report['issues'] if i['code'] == 'practice_duration_needs_review')
    assert (flag['agenda_minutes'], flag['detail_minutes']) == (10, 5)
    assert flag['severity'] == 'review'


@pytest.mark.parametrize('detail', ['Use a 10-minute role-play.', 'Optional: use a 5-minute role-play.',
                                   '5-minute reflection'])
def test_matching_optional_or_unrelated_detail_does_not_raise_practice_conflict(detail):
    report = review('Agenda\n0–40 min | Cycle\n  - 10 minutes of practice\n40–60 min | Break\n### Activities\n' + detail)
    assert 'practice_duration_needs_review' not in codes(report)


def test_multiple_practice_tasks_are_not_assumed_identical():
    report = review('Agenda\n0–40 min | Cycle\n  - 10 minutes of practice\n  - 15 minutes of practice\n40–60 min | Break\n### Activities\n5-minute role-play')
    assert 'practice_identity_unknown' in codes(report)
    assert 'practice_duration_needs_review' not in codes(report)



def test_saved_v2_feedback_roleplay_wording():
    report = review("""Agenda
0–40 min | Guided Practice
  - Rotation: 10 minutes practice, 5 minutes observer feedback, 5 minutes swap/reset...
40–60 min | Break
### Activities & Completion Checks
Task: Conduct a 5-minute feedback role-play using the framework.
""")
    flags = [i for i in report['issues'] if i['code'] == 'practice_duration_needs_review']
    assert len(flags) == 1
    assert flags[0]['agenda_minutes'] == 10
    assert flags[0]['detail_minutes'] == 5
    assert flags[0]['severity'] == 'review'
    assert 'format_switch_needs_review' in codes(report)


@pytest.mark.parametrize('detail', [
    'Optional: Conduct a 5-minute feedback role-play using the framework.',
    'Alternative: Conduct a 5-minute feedback role-play using the framework.',
    'Conduct 5-minute feedback before the role-play.',
    'Conduct a 5-minute observer feedback discussion before practice.',
])
def test_feedback_modifier_does_not_match_alternatives_or_separate_tasks(detail):
    report = review('Agenda\n0–40 min | Guided Practice\n'
                    '  - Rotation: 10 minutes practice, 5 minutes observer feedback, 5 minutes swap/reset...\n'
                    '40–60 min | Break\n### Activities & Completion Checks\n' + detail)
    assert 'practice_duration_needs_review' not in codes(report)
