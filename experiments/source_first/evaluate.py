"""Run fixed synthetic retrieval probes; no network, app state, or provider imports."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile
import time
import socket
from prototype import SourceIndex

HERE = Path(__file__).resolve().parent


def load_fixture():
    expected = (HERE/'fixture.sha256').read_text().split()[0]
    assert hashlib.sha256((HERE/'fixture.json').read_bytes()).hexdigest() == expected
    f = json.loads((HERE/'fixture.json').read_text())
    texts = {}
    for s in f['sources']:
        text = (HERE/s['path']).read_text() if 'path' in s else s['text']
        assert hashlib.sha256(text.encode()).hexdigest() == s['sha256']
        texts[s['id']] = text
    for q in f['queries']:
        for g in q['relevant'] + q['qualifications']:
            assert texts[g['source_id']][g['start']:g['end']] == g['text']
    return f, texts


def includes(b, g):
    return b['source_id'] == g['source_id'] and b['start_char'] <= g['start'] and b['end_char'] >= g['end']


def metrics(result, q, index):
    blocks = {b['id']:b for b in index.blocks(q['scope'])}
    ranked = [blocks[i] for i in result['ranked']]
    gold = q['relevant']
    hits = [int(any(includes(b,g) for g in gold)) for b in ranked]
    recall = sum(any(includes(b,g) for b in ranked) for g in gold)/len(gold) if gold else None
    ideal = sum(1/math.log2(i+2) for i in range(min(10,len(gold))))
    dcg = sum(h/math.log2(i+2) for i,h in enumerate(hits))
    final = result['blocks']
    qgold = q['qualifications']
    required_sections = {b['chapter_or_section'] for b in blocks.values() if any(includes(b,g) for g in gold)}
    required_sources = {g['source_id'] for g in gold}
    return dict(recall_at_10=recall, precision_at_10=sum(hits)/10,
                ndcg_at_10=dcg/ideal if ideal else None,
                context_recall=sum(any(includes(b,g) for b in final) for g in gold)/len(gold) if gold else None,
                qualification_recall=sum(any(includes(b,g) for b in final) for g in qgold)/len(qgold) if qgold else None,
                judged_context_precision=sum(any(includes(b,g) for g in gold) for b in final)/len(final) if final else None,
                required_section_recall=len(required_sections & set(result['sections']))/len(required_sections) if required_sections else None,
                required_source_recall=len(required_sources & set(result['source_ids']))/len(required_sources) if required_sources else None,
                duplicate_ids=len(final)-len({b['id'] for b in final}),
                words=result['word_count'], context_blocks=len(final),
                location_integrity=all(index.db.execute('SELECT text FROM sources WHERE id=?',(b['source_id'],)).fetchone()[0][b['start_char']:b['end_char']]==b['text'] for b in final),
                noanswer_empty=not final if q['kind']=='noanswer' else None)


def run():
    f, texts = load_fixture()
    i = SourceIndex(aliases=f['aliases'])
    for sid,text in texts.items(): i.put(sid,text)
    rows=[]
    for q in f['queries']:
        results={}
        for mode in ['bm25','expanded','fusion','context']:
            result=i.retrieve(q['query'],q['scope'],mode,q['kind'])
            results[mode]={'metrics':metrics(result,q,i), 'result':result}
        rows.append({'id':q['id'],'kind':q['kind'],'modes':results})
    summary={}
    for mode in ['bm25','expanded','fusion','context']:
        ms=[row['modes'][mode]['metrics'] for row in rows]
        summary[mode]={k:statistics.mean(m[k] for m in ms if m[k] is not None) for k in ms[0] if any(m[k] is not None for m in ms)}
    i.close()
    return {'fixture_sha256':(HERE/'fixture.sha256').read_text().split()[0],
            'scope':'26 fixed synthetic feasibility probes; no secret held-out/generalization claim',
            'knowledge_assets_created':0,'provider_calls':0,
            'summary':summary,'queries':rows}


def performance():
    results=[]
    for pages in (100,1000):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'prototype.sqlite3'; i=SourceIndex(path)
            # A reproducible page proxy: 300 words/page, one section + three paragraphs.
            page=lambda n:f'## Page {n}\n\n'+('\n\n'.join(('repair ticket consent capacity measurement '+('workshop records '*47)) for _ in range(3)))
            text='\n\n'.join(page(n) for n in range(pages))
            t=time.perf_counter();i.put('scale',text);index_ms=(time.perf_counter()-t)*1000
            timing={}
            for mode in ['bm25','fusion','context']:
                times=[]
                for n in range(22):
                    # Fresh result-cache key; warm SQLite pages, no memoized-result timings.
                    t=time.perf_counter();i.retrieve('repair consent '+str(n),['scale'],mode)
                    if n>=2:times.append((time.perf_counter()-t)*1000)
                timing[mode]={'p50_ms':statistics.median(times),'p95_ms':sorted(times)[18]}
            results.append({'page_proxies':pages,'words':len(text.split()),'index_ms':index_ms,
                            'index_bytes':path.stat().st_size,'timing':timing})
            i.close()
    import resource
    return {'scales':results,'process_peak_rss_bytes_macos':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'note':'Whole process peak, not isolated parser memory; synthetic page proxies, not rendered PDFs.'}


def deny_network(*args,**kwargs):
    raise AssertionError('Network disabled for offline evaluation')


if __name__=='__main__':
    socket.socket=deny_network;socket.create_connection=deny_network
    output=run();output['performance']=performance()
    (HERE/'results.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(output['summary'],indent=2)); print(json.dumps(output['performance'],indent=2))
