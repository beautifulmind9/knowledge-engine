"""Read-only BM25 over current source text artifacts; no assets or provider calls.

Indexes are request-local, not application persistence. Exact locators refer to
stored extracted text, not original binary bytes. No cached result can outlive a
source change. Deliberately no expansion, fusion or semantic sufficiency scoring.
"""
import hashlib
import re
import sqlite3
from pathlib import Path

from fastapi import HTTPException
from app.db.mock_data import libraries, sources
from app.persistence.factory import get_artifact_store
from app.db.persistence import STORAGE_ROOT
from app.persistence.artifact_paths import contained_locator
from app.services import partition_authority as authority

VERSION = 'source-passages-v1'
MAX_SOURCES = 20
MAX_TEXT = 2_000_000
MAX_SCOPE_TEXT = 8_000_000
STOP = set('a an the and or of to for in on is are be by with what how which can should i me my we do does did it its this that please help about from before after as have not'.split())
LIMITATIONS = [
    'Lexical text matches only; paraphrases can be missed and matches can be irrelevant.',
    'Processing and retrieval do not establish semantic completeness or source support for an answer.',
    'Locations refer to stored extracted text; tables, figures and reading order may be incomplete.',
    'No AI interpretation, extraction or provider request is performed.',
]


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _passages(source, text):
    text_hash = _hash(text)
    version = _hash(f"{VERSION}:{source['id']}:{source.get('generation', '')}:{text_hash}")
    section, blocks = None, []
    for match in re.finditer(r'(?m)^#{1,6}[^\n]*|[^\n]+(?:\n(?!\n|#{1,6} )[^\n]+)*', text):
        body = match.group()
        if re.match(r'^#{1,6}\s+', body):
            section = re.sub(r'^#{1,6}\s+', '', body).strip()
            if len(section) > 500:
                raise HTTPException(413, 'Section label exceeds the read-only preview budget.')
            continue
        words = list(re.finditer(r'\S+', body))
        # Bound long paragraphs without changing a single character of returned text.
        for start in range(0, len(words), 200):
            end = min(start + 200, len(words))
            a = match.start() + words[start].start()
            b = match.start() + words[end-1].end()
            if b - a > 16000:
                raise HTTPException(413, 'A source passage exceeds the read-only preview budget.')
            blocks.append(dict(passage_id=_hash(f'{version}:{a}:{b}')[:24], source_id=source['id'],
                               source_version=version, text_sha256=text_hash, title=source['title'],
                               section=section, start_char=a, end_char=b, text=text[a:b],
                               locator_basis='stored_extracted_text', index=len(blocks), page_start=None))
    return blocks


def _coverage(source, text, store):
    info = dict(source_id=source['id'], title=source['title'], status='indexed_text' if text else 'uncertain_extraction',
                extraction_state=source.get('reading_failure') or ('text_available' if text else 'not_read_or_unavailable'),
                original_available=False, total_pages=None, image_only_pages=[], no_text_pages=[],
                page_mapping='unavailable', limitations=[])
    path = source.get('file_path')
    try:
        path = contained_locator(store, Path(path), STORAGE_ROOT) if path else None
        info['original_available'] = bool(path and store.status(path) == 'artifact')
        if not info['original_available']:
            info['limitations'].append('Original file unavailable; text index is not a complete preservation check.')
            return info, []
        if not text:
            info['status'] = 'preserved_not_indexed'
            info['limitations'].append('No readable text artifact. This read-only preview does not process material; deterministic reading must be completed separately.')
        if source.get('file_type') != '.pdf':
            info['limitations'].append('Text-only representation; image/table structure and full content coverage are uncertain.')
            return info, []
        from pypdf import PdfReader
        with store.materialize(Path(path)) as local:
            reader = PdfReader(str(local))
            info['total_pages'] = len(reader.pages)
            if len(reader.pages) > 200:
                info['limitations'].append('PDF page coverage was not inspected: more than 200 pages.')
                return info, []
            pages, spans, cursor = [], [], 0
            for number, page in enumerate(reader.pages, 1):
                page_text = (page.extract_text() or '').strip()
                if not page_text:
                    info['no_text_pages'].append(number)
                    # Image resources establish preserved images, not understood meaning.
                    if len(page.images):
                        info['image_only_pages'].append(number)
                else:
                    if pages:
                        cursor += 2
                    spans.append((cursor, cursor + len(page_text), number))
                    pages.append(page_text)
                    cursor += len(page_text)
            if '\n\n'.join(pages) == text:
                info['page_mapping'] = 'verified_text_alignment'
            else:
                spans = []
                info['limitations'].append('Stored text differs from current PDF extraction; page mapping unavailable.')
            if info['no_text_pages']:
                info['limitations'].append('Pages without extractable text are preserved but not text-searchable; images are not interpreted.')
            info['limitations'].append('Text-bearing pages can still contain unindexed images and flattened tables.')
            return info, spans
    except Exception:
        info['limitations'].append('Original/page coverage could not be verified; no completeness conclusion is available.')
        return info, []


def load_source_scope(source_ids=None, library_id=None):
    if library_id and not any(l['id'] == library_id for l in libraries):
        raise HTTPException(404, 'Library not found.')
    requested = set(source_ids or [])
    selected = [authority.source(s) for s in sources
                if (not requested or s['id'] in requested)
                and (not library_id or s.get('library_id') == library_id)]
    if requested and requested != {s['id'] for s in selected}:
        raise HTTPException(404, 'Source not found in selected scope.')
    if len(selected) > MAX_SOURCES:
        raise HTTPException(413, 'Select at most 20 sources for this read-only preview.')
    store = get_artifact_store()
    blocks, coverage, total = [], [], 0
    for source in sorted(selected, key=lambda s: s['id']):
        text = ''
        try:
            path = source.get('extracted_text_path')
            if path:
                path = contained_locator(store, Path(path), STORAGE_ROOT)
                if store.status(path) == 'artifact':
                    text = store.read_text(path)
        except Exception:
            text = ''
        if len(text) > MAX_TEXT or total + len(text) > MAX_SCOPE_TEXT:
            raise HTTPException(413, 'Source text exceeds this preview budget; use a smaller scope.')
        total += len(text)
        info, spans = _coverage(source, text, store)
        current = _passages(source, text)
        for b in current:
            # A page label is returned only when exact text alignment is established.
            b['page_start'] = next((page for a,z,page in spans if a <= b['start_char'] < z), None)
        info['passage_count'] = len(current)
        info['library_id'] = source.get('library_id')
        info['source_version'] = current[0]['source_version'] if current else None
        info['text_sha256'] = _hash(text) if text else None
        if text and not current:
            info['limitations'].append('No non-heading text passages were available to index.')
        coverage.append(info); blocks.extend(current)
    return blocks, coverage


def search_passages(query, source_ids=None, library_id=None, limit=10, neighbors=False, *, _loaded=None):
    blocks, coverage = _loaded if _loaded is not None else load_source_scope(source_ids, library_id)
    tokens = list(dict.fromkeys(t for t in re.findall(r'\w+', query.casefold()) if len(t)>1 and t not in STOP))[:64]
    items = []
    if tokens and blocks:
        # Isolated in-memory derived index: no schema migration or persisted index/cache.
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE VIRTUAL TABLE passages USING fts5(pid UNINDEXED, heading, body)')
            db.executemany('INSERT INTO passages VALUES (?,?,?)',
                           [(b['passage_id'], b['section'] or '', b['text']) for b in blocks])
            expression = ' OR '.join('"'+t.replace('"','""')+'"' for t in tokens)
            ranked = db.execute('SELECT pid,bm25(passages,0,2,1) FROM passages WHERE passages MATCH ? ORDER BY 2,pid LIMIT ?', (expression, limit)).fetchall()
            by_id = {b['passage_id']: b for b in blocks}
            ranked_ids = {pid for pid, _ in ranked}
            context_seen = set(ranked_ids)
            for rank, (pid, score) in enumerate(ranked, 1):
                b = by_id[pid]
                item = {**b, 'rank':rank, 'bm25':score, 'neighbors':[]}
                if neighbors:
                    item['neighbors'] = [n for n in blocks if n['source_id']==b['source_id']
                                         and n['section']==b['section'] and abs(n['index']-b['index'])==1
                                         and n['passage_id'] not in context_seen]
                    context_seen.update(n['passage_id'] for n in item['neighbors'])
                items.append(item)
        except sqlite3.OperationalError as error:
            raise HTTPException(503, 'Local full-text search is unavailable.') from error
        finally:
            db.close()
    return dict(items=items, count=len(items), coverage=coverage, limitations=LIMITATIONS,
                index_mode='request_local_rebuilt', query_terms=tokens,
                query_terms_limited=len(set(t for t in re.findall(r'\w+', query.casefold()) if len(t)>1 and t not in STOP))>64,
                note='Ranked passages, not an AI answer or a completeness assessment.')
