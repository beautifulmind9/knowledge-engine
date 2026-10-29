"""Standalone synthetic-source retrieval. No app imports, assets or provider clients."""
from bisect import bisect_left
from copy import deepcopy
import hashlib
import json
import re
import sqlite3

VERSION = 'source-first-offline-v1'
STOP = set('a an the and or of to for in on is are be by with what how which can should i me my we do does did it its this that please help about from before after as have not'.split())


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def terms(text):
    return list(dict.fromkeys(w for w in re.findall(r'[\w]+', text.casefold()) if len(w) > 1 and w not in STOP))


def passages(sid, text, parser='paragraph-v1'):
    """Non-overlapping exact source slices with existing KE word-index conventions."""
    version = fingerprint([sid, text, parser])
    words = [m.start() for m in re.finditer(r'\S+', text)]
    result, section = [], 'Unsectioned'
    for m in re.finditer(r'[^\n]+(?:\n(?!\n)[^\n]+)*', text):
        body = m.group()
        if re.match(r'^#{1,6}\s+', body):
            section = re.sub(r'^#{1,6}\s+', '', body)
            continue
        start, end = m.span()
        result.append(dict(id=fingerprint([sid, version, start, end])[:24], source_id=sid,
                           source_version=version, chapter_or_section=section, text=body,
                           start_char=start, end_char=end, chunk_index=len(result)+1,
                           start_word_index=bisect_left(words, start),
                           end_word_index=bisect_left(words, end), word_count=len(body.split()),
                           page=None, locator_basis='decoded-source-text'))
    return result


class SourceIndex:
    def __init__(self, path=':memory:', aliases=None):
        # Only open a new file or a verified prototype file, never application DBs.
        from pathlib import Path
        if path != ':memory:' and Path(path).exists():
            probe = sqlite3.connect(f'file:{Path(path).resolve()}?mode=ro', uri=True)
            try:
                if probe.execute('SELECT value FROM prototype_meta WHERE key="magic"').fetchone() != (VERSION,):
                    raise ValueError('Not a prototype index')
            finally:
                probe.close()
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS prototype_meta(key TEXT PRIMARY KEY, value TEXT)')
        self.db.execute('INSERT OR IGNORE INTO prototype_meta VALUES (?,?)', ('magic', VERSION))
        self.db.execute('CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, text TEXT, parser TEXT, version TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS blocks(id TEXT PRIMARY KEY, sid TEXT, payload TEXT)')
        self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, sid UNINDEXED, heading, body)')
        self.db.commit()
        self.aliases = aliases or {}
        self.cache = {}

    def close(self):
        self.db.close()

    def put(self, sid, text, parser='paragraph-v1'):
        blocks = passages(sid, text, parser)
        version = fingerprint([sid, text, parser])
        with self.db:
            self.db.execute('DELETE FROM search WHERE sid=?', (sid,))
            self.db.execute('DELETE FROM blocks WHERE sid=?', (sid,))
            self.db.execute('INSERT OR REPLACE INTO sources VALUES (?,?,?,?)', (sid, text, parser, version))
            for b in blocks:
                self.db.execute('INSERT INTO blocks VALUES (?,?,?)', (b['id'], sid, json.dumps(b)))
                self.db.execute('INSERT INTO search VALUES (?,?,?,?)', (b['id'], sid, b['chapter_or_section'], b['text']))
        self.cache.clear()
        return blocks

    def remove(self, sid):
        with self.db:
            for table, column in [('search', 'sid'), ('blocks', 'sid'), ('sources', 'id')]:
                self.db.execute(f'DELETE FROM {table} WHERE {column}=?', (sid,))
        self.cache.clear()

    def blocks(self, scope):
        return sorted((json.loads(payload) for sid, payload in self.db.execute('SELECT sid,payload FROM blocks') if sid in scope),
                      key=lambda b: (b['source_id'], b['chunk_index']))

    def plan(self, query, expanded):
        original = terms(query)
        variants = [original] if original else []
        if expanded:
            for phrase, alias in self.aliases.items():
                if re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', query.casefold()):
                    variants.append(terms(alias))
            # A heading/phrase perspective is lexical, not semantic decomposition.
            quoted = re.findall(r'"([^"\n]+)"', query)
            variants.extend(terms(p) for p in quoted)
        unique = []
        seen = set()
        for v in variants:
            key = tuple(sorted(v))
            if key and key not in seen:
                unique.append(v)
                seen.add(key)
        return unique[:4]

    def search(self, variant, scope):
        if not variant or not scope:
            return []
        expression = ' OR '.join('"' + t.replace('"', '""') + '"' for t in variant)
        placeholders = ','.join('?' for _ in scope)
        rows = self.db.execute(f'SELECT id,bm25(search,0,0,2,1) FROM search WHERE search MATCH ? AND sid IN ({placeholders}) ORDER BY 2,id LIMIT 20', (expression, *scope))
        return [{'id':bid, 'bm25':score} for bid, score in rows]

    def retrieve(self, query, scope, mode='bm25', kind='targeted', max_blocks=12, max_words=6000):
        if mode not in {'bm25', 'expanded', 'fusion', 'context'}:
            raise ValueError('Unknown retrieval mode')
        if kind not in {'targeted', 'broad', 'cross', 'noanswer'}:
            raise ValueError('Unknown question kind')
        if not 1 <= max_blocks <= 12 or not 1 <= max_words <= 6000:
            raise ValueError('Invalid bounded-context budget')
        scope = sorted(set(scope))
        corpus = list(self.db.execute('SELECT id,version FROM sources ORDER BY id'))
        if not set(scope) <= {sid for sid, _ in corpus}:
            raise ValueError('Scope contains unknown/deleted sources')
        key = fingerprint([VERSION, corpus, scope, query, mode, kind, max_blocks, max_words, self.aliases])
        if key in self.cache:
            result = deepcopy(self.cache[key]); result['cache_hit'] = True
            return result
        variants = self.plan(query, mode != 'bm25')
        lists = [self.search(v, scope) for v in variants]
        scores, best = {}, {}
        for li, hits in enumerate(lists):
            for rank, hit in enumerate(hits, 1):
                bid = hit['id']; scores[bid] = scores.get(bid, 0) + 1/(60 + rank)
                best[bid] = min(best.get(bid, (999, 999)), (rank, li))
        if mode in {'fusion', 'context'}:
            ranked = sorted(scores, key=lambda bid: (-scores[bid], bid))
        else:
            ranked = sorted(best, key=lambda bid: (*best[bid], bid))
        all_blocks = self.blocks(scope); byid = {b['id']: b for b in all_blocks}
        seeds = list(ranked)
        if mode == 'context' and kind == 'broad':
            groups = {}
            for b in all_blocks:
                groups.setdefault((b['source_id'], b['chapter_or_section']), []).append(b['id'])
            seeds = [next((bid for bid in ranked if bid in ids), ids[0]) for ids in groups.values()]
            seeds += ranked
        if mode == 'context' and kind == 'cross':
            # Only sources with actual lexical hits are eligible, never force no-hit material.
            seeds = [next(bid for bid in ranked if byid[bid]['source_id'] == sid)
                     for sid in scope if any(byid[bid]['source_id'] == sid for bid in ranked)] + ranked
        seeds = list(dict.fromkeys(seeds))[:(min(4, max_blocks) if mode == 'context' and kind not in {'broad', 'cross'} else max_blocks)]
        candidates = list(seeds)
        if mode == 'context':
            for bid in seeds:
                b = byid[bid]
                candidates += [n['id'] for n in all_blocks if n['source_id'] == b['source_id']
                               and n['chapter_or_section'] == b['chapter_or_section']
                               and abs(n['chunk_index'] - b['chunk_index']) == 1]
        selected, excluded, used, seen = [], [], 0, set()
        for bid in candidates:
            if bid in seen:
                continue
            seen.add(bid); b = byid[bid]
            words = len(b['text'].split()) + len(b['chapter_or_section'].split())
            if len(selected) >= max_blocks or used + words > max_words:
                excluded.append(bid); continue
            selected.append(b); used += words
        # Neighbors are recorded as context, not scored matches.
        result = dict(mode=mode, query=query, variants=variants, ranked=ranked[:10],
                      ranked_lists=lists, blocks=selected, excluded=excluded, word_count=used,
                      sections=sorted(set(b['chapter_or_section'] for b in selected)),
                      source_ids=sorted(set(b['source_id'] for b in selected)),
                      omitted_sections=sorted(set(b['chapter_or_section'] for b in all_blocks) - set(b['chapter_or_section'] for b in selected)),
                      cache_hit=False, context_hash=fingerprint(selected),
                      limit_note='Bounded retrieved context; not whole-source coverage or an answer.',
                      corpus_fingerprint=fingerprint(corpus))
        self.cache[key] = deepcopy(result)
        return result
