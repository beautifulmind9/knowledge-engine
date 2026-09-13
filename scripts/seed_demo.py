"""Populate a running local API with original synthetic examples; makes no AI calls."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
import uuid

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Knowledge Engine — synthetic demo'


def seed(base_url):
    parsed = urlsplit(base_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password:
        raise ValueError('Demo seeding supports only a local HTTP server.')
    opener = build_opener(ProxyHandler({}))

    def call(path, body=None, method=None, upload=None):
        headers = {}
        data = None
        if upload:
            boundary = 'ke-' + uuid.uuid4().hex
            data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{upload.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + upload.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        elif body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        request = Request(base_url.rstrip('/') + path, data=data, headers=headers, method=method or ('POST' if data is not None else 'GET'))
        try:
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(error.read().decode()) from error

    existing = next((l for l in call('/libraries')['items'] if l['name'] == NAME), None)
    if existing:
        return {'library_id': existing['id'], 'status': 'Demo already exists; no records changed.'}
    library = call('/libraries', {'name': NAME, 'description': 'Original synthetic fixtures; manually imported, not AI generated.'})
    source_ids = []
    for filename, title, statements in [
        ('facilitation.md', 'Facilitation notes', [
            'Use practice breaks to help participants retain learning.',
            'Set a specific learning goal before choosing activities.',
            'For a guided training session, explain the method before participants begin practice.']),
        ('learning-lab.html', 'Learning lab notes', [
            'Use practice breaks to help participants retain learning.',
            'Ask participants to explain their next action in their own words to check understanding.',
            'For a discovery session, do not explain the method before participants begin practice.'])
    ]:
        source = call('/sources', {'library_id': library['id'], 'title': title, 'author': 'Original synthetic demo'})
        sid = source['id']; source_ids.append(sid)
        call(f'/sources/{sid}/upload', upload=ROOT / 'examples' / filename)
        call(f'/sources/{sid}/process', method='POST')
        chunk = call(f'/sources/{sid}/chunks')['items'][0]
        job = call('/knowledge-extractions', {'source_id': sid, 'chunk_id': chunk['id']})['job']
        assets = [{'asset_type': 'principle', 'source_id': sid, 'chunk_id': chunk['id'],
                   'title': statement, 'what_it_says': statement, 'evidence': statement,
                   'keywords': ['practice', 'learning', 'participants'], 'confidence_score': 4} for statement in statements]
        call(f"/knowledge-extractions/{job['id']}/results", {'assets': assets})
    brief = {'situation': 'Prepare a mixed-experience learning session', 'goal': 'Choose practice breaks and check understanding',
             'audience': 'New facilitators', 'source_ids': source_ids, 'library_id': library['id'], 'output_type': 'playbook', 'tone_or_style': 'Plain and encouraging'}
    prepared = call('/workshops/prepare', brief)
    used = [{'asset_id': g['canonical_asset']['id'], 'usage_note': 'Applies this learning principle to the practice session.'}
            for g in prepared['knowledge_units'] if 'practice breaks' in g['canonical_asset']['what_it_says'] or 'own words' in g['canonical_asset']['what_it_says']]
    saved = call('/outputs', {'brief': brief, 'output': {
        'title': 'A focused practice session — synthetic demo', 'output_type': 'playbook',
        'content': 'Purpose\nHelp participants retain learning and check understanding.\n\nPrerequisites\nChoose a skill participants can practice.\n\nSteps\n1. Introduce the task.\n2. Alternate guided practice with breaks.\n3. Ask each participant to explain their next action in their own words.\n\nChecks\nListen for a clear next action; clarify misunderstandings.\n\nExceptions\nChoose guided instruction or discovery deliberately; the notes describe different contexts.',
        'applied_knowledge': used, 'design_choices': ['This sequence is a manually authored demo adaptation; the sources do not prescribe its timing.']}})
    revised = call(f"/outputs/{saved['id']}/revise", {'instruction': 'Make the checklist more concise', 'content':
        'Purpose\nPractice a skill and check understanding.\n\nPrerequisites\nChoose one skill.\n\nSteps\n1. Practice with breaks.\n2. Explain the next action in your own words.\n\nChecks\nClarify unclear next actions.\n\nExceptions\nAdapt guided instruction or discovery to the session context.'})
    return {'library_id': library['id'], 'source_ids': source_ids, 'output_id': revised['id'],
            'versions': 2, 'agreements': len(prepared['synthesis_context']['agreements']),
            'tensions': len(prepared['synthesis_context']['tensions']), 'ai_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    print(json.dumps(seed(args.url), indent=2))
