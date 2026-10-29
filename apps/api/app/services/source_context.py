"""Deterministic source-context snapshots. No provider, asset, or durable DB writes."""
from copy import deepcopy
from collections import deque
import hashlib
import json

from fastapi import HTTPException
from app.services.source_search import load_source_scope, search_passages
from app.db.mock_data import sources
from app.services import partition_authority as authority
from app.persistence.factory import get_artifact_store
from app.persistence.artifact_paths import contained_locator
from app.db.persistence import STORAGE_ROOT
from pathlib import Path

CONTRACT = 'source-context-v1'
MAX_SERIALIZED_BYTES = 128000


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def fingerprint(package):
    return hashlib.sha256(canonical_bytes({k:v for k,v in package.items() if k!='fingerprint'})).hexdigest()


def _seal(package):
    package['fingerprint'] = '0'*64
    package['size']['serialized_bytes'] = 0
    # A fixed-length digest placeholder avoids a self-referential size/hash.
    for _ in range(8):
        actual = len(canonical_bytes(package))
        if actual == package['size']['serialized_bytes']:
            break
        package['size']['serialized_bytes'] = actual
    package['fingerprint'] = fingerprint(package)
    if len(canonical_bytes(package)) > MAX_SERIALIZED_BYTES:
        raise HTTPException(413, 'Context metadata exceeds the snapshot budget; reduce source scope.')
    return package


def build_source_context(question, source_ids=None, library_id=None, strategy='targeted',
                         max_passages=None, max_words=6000, max_chars=48000):
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError('Question must contain 1 to 2000 characters.')
    if strategy not in {'targeted','broad'}:
        raise ValueError('Unknown context strategy.')
    if max_passages is None:
        max_passages = 64 if strategy == 'broad' else 24
    if not (1 <= max_passages <= 64 and 1 <= max_words <= 6000 and 1 <= max_chars <= 48000):
        raise ValueError('Invalid context size limits.')
    catalog, coverage = load_source_scope(source_ids, library_id)
    if strategy == 'broad' and len(coverage)!=1:
        raise HTTPException(400, 'Broad context requires exactly one selected source.')
    # Bind the context to preserved original bytes as well as the extracted-text version.
    store = get_artifact_store()
    for info in coverage:
        info['original_sha256'] = None
        if info['original_available']:
            try:
                record = authority.source(next(s for s in sources if s['id']==info['source_id']))
                path = contained_locator(store, Path(record['file_path']), STORAGE_ROOT)
                digest = hashlib.sha256(); size = 0
                with store.open_binary_read(path) as stream:
                    while part := stream.read(1024*1024):
                        size += len(part)
                        if size > 50_000_000:
                            raise ValueError('Original exceeds the context fingerprint budget.')
                        digest.update(part)
                info['original_sha256'] = digest.hexdigest()
            except Exception:
                info['limitations'].append('Original byte fingerprint unavailable; source snapshot reuse cannot be verified.')
    result = search_passages(question, source_ids, library_id, limit=10, _loaded=(catalog,coverage))
    by_id = {b['passage_id']: b for b in catalog}
    chosen, rejected, roles, neighbor_of = {}, set(), {}, {}
    words = chars = 0

    def add(block, role, parent=None):
        nonlocal words, chars
        pid = block['passage_id']
        if pid not in chosen:
            wc, cc = len(block['text'].split()), len(block['text'])
            if len(chosen)>=max_passages or words+wc>max_words or chars+cc>max_chars:
                rejected.add(pid)
                return False
            chosen[pid] = block
            words += wc; chars += cc
        roles.setdefault(pid,set()).add(role)
        if parent:
            neighbor_of.setdefault(pid,set()).add(parent)
        return True

    # Protect every fitting ranked hit before section sampling or neighbors.
    for hit in result['items']:
        add(by_id[hit['passage_id']], 'ranked_hit')
    sections = {}
    for block in catalog:
        sections.setdefault((block['source_id'], block['section']), []).append(block)
    if strategy == 'broad':
        represented = {(b['source_id'],b['section']) for b in chosen.values()}
        for key, group in sections.items():
            if key not in represented:
                add(group[0], 'section_representative')
        # Round-robin additional source paragraphs, not only one token per heading.
        # The small frozen source fits whole; long sources remain bounded/partial.
        queue = deque(iter(group) for group in sections.values())
        while queue:
            group = queue.popleft()
            block = next(group, None)
            if block is not None:
                add(block, 'section_context')
                queue.append(group)
    for hit in result['items']:
        pid = hit['passage_id']
        if pid not in chosen:
            continue
        block = by_id[pid]
        for candidate in catalog:
            if candidate['source_id']==block['source_id'] and candidate['section']==block['section'] and abs(candidate['index']-block['index'])==1:
                add(candidate, 'neighbor', pid)
    ranked = {b['passage_id']:b['rank'] for b in result['items']}
    ref = lambda b: 'sp_'+b['passage_id']
    evidence = []
    for block in sorted(chosen.values(),key=lambda b:(b['source_id'],b['start_char'])):
        evidence.append({**block, 'evidence_ref':ref(block), 'roles':sorted(roles[block['passage_id']]),
                         'retrieval_rank':ranked.get(block['passage_id']),
                         'neighbor_of':[ref(by_id[pid]) for pid in sorted(neighbor_of.get(block['passage_id'],set()))]})
    represented = {(b['source_id'],b['section']) for b in chosen.values()}
    missing_sections = [dict(source_id=sid, section=section) for sid,section in sections if (sid,section) not in represented]
    excluded_ranked = [hit['passage_id'] for hit in result['items'] if hit['passage_id'] not in chosen]
    unavailable = any(c['status']!='indexed_text' or not c.get('original_sha256') for c in coverage)
    state = ('insufficient_evidence' if unavailable or excluded_ranked or (not evidence and bool(catalog))
             else 'context_available')
    if not evidence and not result['items'] and not unavailable:
        state = 'no_matches'
    package = dict(contract=CONTRACT, question=question, strategy=strategy, state=state,
                   scope=dict(requested_source_ids=sorted(set(source_ids or [])), library_id=library_id,
                              resolved_source_ids=sorted(c['source_id'] for c in coverage)),
                   sources=deepcopy(coverage), evidence=evidence,
                   retrieval=dict(method='bm25_original_query', limit=10,
                                  query_terms=result['query_terms'], query_terms_limited=result['query_terms_limited'],
                                  ranked_passage_ids=[h['passage_id'] for h in result['items']],
                                  selection='ranked-first; section-round-robin for broad; immediate same-section neighbors',
                                  broad_without_lexical_hits=strategy=='broad' and not result['items']),
                   limits=dict(max_passages=max_passages,max_words=max_words,max_chars=max_chars,
                               max_serialized_bytes=MAX_SERIALIZED_BYTES),
                   size=dict(passages=len(evidence), evidence_words=words,evidence_chars=chars),
                   truncation=dict(passage_text_truncated=False, budget_limited=bool(rejected),
                                   excluded_ranked_passage_ids=excluded_ranked,
                                   budget_excluded_count=len(rejected-chosen.keys()),
                                   omitted_passage_count=len(catalog)-len(chosen),
                                   unrepresented_section_count=len(missing_sections),
                                   unrepresented_sections=missing_sections[:64],
                                   section_diagnostics_limited=len(missing_sections)>64),
                   limitations=result['limitations']+[
                       'Evidence references verify identity and exact text, not entailment or semantic completeness.',
                       'No semantic sufficiency score is computed. context_available does not mean the question is answerable.',
                       'A fingerprint detects changes; it is not an authorization token or an authenticated server snapshot.',
                       'Word/character limits are not a verified Gemini token budget. No provider request is prepared.',
                   ])
    return _seal(package)


def verify_snapshot(package):
    """Verify digest AND reproduce against live scope/source versions before reuse.

    No trusted client-supplied evidence. Missing/changed sources, metadata,
    scope or text fail closed. Historical JSON stays readable but is stale.
    """
    try:
        if any(not source.get('original_sha256') or not source.get('source_version') for source in package['sources']):
            return False
        if package['contract']!=CONTRACT or fingerprint(package)!=package['fingerprint']:
            return False
        scope, limits = package['scope'],package['limits']
        current = build_source_context(package['question'], scope['requested_source_ids'],scope['library_id'],
                                       package['strategy'], limits['max_passages'],limits['max_words'],limits['max_chars'])
        return current['fingerprint']==package['fingerprint']
    except (KeyError,TypeError,ValueError,HTTPException):
        return False


def validate_citations(package, citations):
    """Exact source-absolute [start,end) quotes inside an included evidence item.

    Checks references supplied by a future caller, not whether claims are true.
    Caller must still enforce server-owned snapshots and claim-level citation use.
    """
    if not verify_snapshot(package):
        raise ValueError('Source context is invalid or stale; no citations accepted.')
    if not isinstance(citations,list):
        raise ValueError('Citations must be a list of reference/span/quote objects.')
    evidence = {e['evidence_ref']:e for e in package['evidence']}
    accepted = []
    for citation in citations:
        if not isinstance(citation,dict):
            raise ValueError('Invalid source citation object.')
        item = evidence.get(citation.get('evidence_ref'))
        start,end,quote = citation.get('start_char'),citation.get('end_char'),citation.get('quote')
        if not item or type(start) is not int or type(end) is not int or not isinstance(quote,str):
            raise ValueError('Invalid source citation reference.')
        if not item['start_char']<=start<end<=item['end_char'] or item['text'][start-item['start_char']:end-item['start_char']]!=quote:
            raise ValueError('Source citation span or quote does not match supplied evidence.')
        accepted.append(dict(evidence_ref=item['evidence_ref'],source_id=item['source_id'],
                             source_version=item['source_version'],start_char=start,end_char=end,quote=quote))
    return accepted
