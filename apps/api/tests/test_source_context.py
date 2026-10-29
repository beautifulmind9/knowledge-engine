from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from app.db import mock_data as db
from app.services import ai_gateway
from app.services.source_context import build_source_context, verify_snapshot, validate_citations, canonical_bytes, fingerprint
from test_source_search import upload, ROOT


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a,**k):raise AssertionError('Context assembly must not call Gemini')
    monkeypatch.setattr(ai_gateway,'generate',deny)


@pytest.fixture
def material(client):
    text=(ROOT/'acceptance/extraction_quality_2026-10-17/source.md').read_text()
    return upload(client,text)[0],text


def context(client,sid,q='consent inspect replace parts',**options):
    r=client.get('/source-context',params={'q':q,'source_id':sid,**options})
    assert r.status_code==200,r.text
    return r.json()


def test_zero_assets_exact_snapshots_and_citations(client,material):
    s,text=material;p=context(client,s['id'])
    assert not db.knowledge_assets and not db.extraction_jobs
    assert p['question']=='consent inspect replace parts' and p['state']=='context_available'
    assert p['size']['serialized_bytes']==len(canonical_bytes(p))
    assert verify_snapshot(p)
    for e in p['evidence']:
        assert text[e['start_char']:e['end_char']]==e['text']
        assert e['source_id']==s['id'] and e['source_version']
        citation={'evidence_ref':e['evidence_ref'],'start_char':e['start_char'],'end_char':e['end_char'],'quote':e['text']}
        assert validate_citations(p,[citation])[0]['source_id']==s['id']
    assert any('Consent to inspect is not consent to replace' in e['text'] for e in p['evidence'])


@pytest.mark.parametrize('corruption',['quote','span','unknown_ref','tamper','overlap'])
def test_reject_corrupted_citation_or_snapshot(client,material,corruption):
    s,_=material;p=context(client,s['id']);e=p['evidence'][0]
    c={'evidence_ref':e['evidence_ref'],'start_char':e['start_char'],'end_char':e['end_char'],'quote':e['text']}
    if corruption=='quote':c['quote']+=' unsupported'
    if corruption=='span':c['start_char']-=1
    if corruption=='unknown_ref':c['evidence_ref']='sp_unknown'
    if corruption=='tamper':
        p['evidence'][0]['text']='invented source text';p['fingerprint']=fingerprint(p)
    if corruption=='overlap':
        p['evidence'].append(deepcopy(e));p['fingerprint']=fingerprint(p)
    with pytest.raises(ValueError):validate_citations(p,[c])


def test_stable_references_fingerprints_neighbor_links_and_order(client,material):
    s,_=material;a=context(client,s['id']);b=context(client,s['id'])
    assert a==b
    refs=[e['evidence_ref'] for e in a['evidence']]
    assert len(refs)==len(set(refs))
    assert [(e['source_id'],e['start_char']) for e in a['evidence']]==sorted((e['source_id'],e['start_char']) for e in a['evidence'])
    assert all(set(e['neighbor_of'])<=set(refs) for e in a['evidence'])
    spans=sorted((e['start_char'],e['end_char']) for e in a['evidence'])
    assert all(x[1]<=y[0] for x,y in zip(spans,spans[1:]))
    assert any('neighbor' in e['roles'] for e in a['evidence'])


def test_scope_validation(client):
    a,al=upload(client,'# A\n\nconsent before replacement')
    b,bl=upload(client,'# B\n\nconsent after inspection')
    p=context(client,a['id'],library_id=al['id'])
    assert p['scope']['resolved_source_ids']==[a['id']]
    assert client.get('/source-context',params={'q':'consent','source_id':a['id'],'library_id':bl['id']}).status_code==404
    assert client.get('/source-context',params=[('q','consent'),('source_id',a['id']),('source_id',b['id']),('strategy','broad')]).status_code==400


@pytest.mark.parametrize('change',['text','original','delete','scope'])
def test_version_invalidation(client,material,change):
    s,_=material;p=context(client,s['id'])
    source=next(x for x in db.sources if x['id']==s['id'])
    if change=='text':Path(source['extracted_text_path']).write_text('Changed consent text')
    if change=='original':
        with Path(source['file_path']).open('ab') as f:f.write(b'\nchanged original')
    if change=='delete':db.sources.remove(source)
    if change=='scope':p['scope']['library_id']='missing';p['fingerprint']=fingerprint(p)
    assert not verify_snapshot(p)


def test_size_limits_and_no_unnecessary_ranked_loss(client,material):
    s,_=material
    hits=client.get('/source-search',params={'q':'owner repairer responsibilities','source_id':s['id']}).json()['items']
    p=context(client,s['id'],'owner repairer responsibilities',strategy='broad',max_passages=12)
    assert {h['passage_id'] for h in hits}<={e['passage_id'] for e in p['evidence']}
    assert p['size']['passages']<=12 and p['size']['evidence_words']<=6000
    tiny=context(client,s['id'],max_words=1,max_chars=20,max_passages=1)
    assert tiny['state']=='insufficient_evidence' and tiny['truncation']['budget_limited']
    assert tiny['truncation']['excluded_ranked_passage_ids']
    assert not tiny['truncation']['passage_text_truncated']
    assert client.get('/source-context',params={'q':'x','source_id':s['id'],'max_words':6001}).status_code==422


def test_no_matches_mismatch_and_unavailable_states(client,material):
    s,_=material
    assert context(client,s['id'],'lunar isotope spectroscopy')['state']=='no_matches'
    p=context(client,s['id'],'How is informed assent delimited before disassembly?')
    # Explicit characterization: no semantic paraphrase matching is implemented.
    assert not any('Consent to inspect is not consent to replace' in e['text'] for e in p['evidence'])
    unread,_=upload(client,'Unread original preserved',process=False)
    p=context(client,unread['id'],'original')
    assert p['state']=='insufficient_evidence' and p['sources'][0]['status']=='preserved_not_indexed'


def test_context_preserves_extraction_first_state(client,knowledge):
    before=json.dumps([db.sources,db.extraction_jobs,db.knowledge_assets,db.outputs,db.usage],sort_keys=True)
    p=context(client,knowledge['source_id'],'practice')
    assert p['evidence']
    assert json.dumps([db.sources,db.extraction_jobs,db.knowledge_assets,db.outputs,db.usage],sort_keys=True)==before


def test_context_reproducible_across_real_processes(tmp_path):
    import os,subprocess,sys
    script=r"""
import json,sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.services.source_context import verify_snapshot
record=Path(sys.argv[2])
with TestClient(app) as c:
 if sys.argv[1]=='create':
  lib=c.post('/libraries',json={'name':'Context restart'}).json()
  s=c.post('/sources',json={'library_id':lib['id'],'title':'Context'}).json()
  assert c.post('/sources/'+s['id']+'/upload',files={'file':('context.md','# Consent\n\nConsent before replacement.\n\nInspection is not replacement.','text/markdown')}).status_code==200
  assert c.post('/sources/'+s['id']+'/process').status_code==200
  p=c.get('/source-context',params={'q':'consent','source_id':s['id']}).json()
  assert p['evidence'];record.write_text(json.dumps({'source':s['id'],'package':p}))
 else:
  old=json.loads(record.read_text());p=c.get('/source-context',params={'q':'consent','source_id':old['source']}).json()
  assert p==old['package'] and verify_snapshot(old['package'])
"""
    env=dict(os.environ,KNOWLEDGE_ENGINE_STORAGE=str(tmp_path/'storage'),PYTHONDONTWRITEBYTECODE='1')
    env.pop('GEMINI_API_KEY',None);env.pop('KNOWLEDGE_ENGINE_DATABASE_URL',None)
    for action in ['create','check']:
        run=__import__('subprocess').run([sys.executable,'-c',script,action,str(tmp_path/'package.json')],cwd=ROOT/'apps/api',env=env,capture_output=True,text=True)
        assert run.returncode==0,run.stderr


def test_frozen_context_benchmark(client):
    import os,statistics
    folder=ROOT/'experiments/source_first'
    expected=(folder/'fixture.sha256').read_text().split()[0]
    assert hashlib.sha256((folder/'fixture.json').read_bytes()).hexdigest()==expected
    f=json.loads((folder/'fixture.json').read_text());ids={}
    for source in f['sources']:
        text=(folder/source['path']).read_text() if 'path' in source else source['text']
        ids[source['id']]=upload(client,text,source['id']+'.md')[0]['id']
    rows=[]
    for q in f['queries']:
        scope=[ids[x] for x in q['scope']]
        baseline=client.get('/source-search',params=[('q',q['query'])]+[('source_id',s) for s in scope]).json()
        strategies=['targeted','broad'] if q['kind']=='broad' else ['targeted']
        def recall(evidence,labels):
            if not labels:return None
            return sum(any(e['source_id']==ids[g['source_id']] and e['start_char']<=g['start'] and e['end_char']>=g['end'] for e in evidence) for g in labels)/len(labels)
        gold_sections={e['section'] for e in _all_blocks(scope) if any(e['source_id']==ids[g['source_id']] and e['start_char']<=g['start'] and e['end_char']>=g['end'] for g in q['relevant'])}
        modes={}
        for strategy in strategies:
            variants=[None,12] if strategy=='broad' else [None]
            for cap in variants:
                options=[('q',q['query']),('strategy',strategy)]+[('source_id',sid) for sid in scope]+([('max_passages',cap)] if cap else [])
                response=client.get('/source-context',params=options);assert response.status_code==200,response.text
                p=response.json();name=strategy+('_12' if cap else '')
                modes[name]=dict(recall=recall(p['evidence'],q['relevant']),qualification_recall=recall(p['evidence'],q['qualifications']),
                                 required_section_recall=len(gold_sections & {e['section'] for e in p['evidence']})/len(gold_sections) if gold_sections else None,
                                 state=p['state'],words=p['size']['evidence_words'],chars=p['size']['evidence_chars'],passages=p['size']['passages'],
                                 bytes=p['size']['serialized_bytes'],omitted=p['truncation']['omitted_passage_count'],
                                 lost_ranked=len(set(e['passage_id'] for e in baseline['items'])-{e['passage_id'] for e in p['evidence']}))
        rows.append(dict(id=q['id'],kind=q['kind'],baseline_recall=recall(baseline['items'],q['relevant']),modes=modes))
    assert not db.knowledge_assets and not db.extraction_jobs
    report=os.environ.get('KE_CONTEXT_REPORT')
    if report:Path(report).write_text(json.dumps({'fixture_sha256':expected,'queries':rows},indent=2))


def _all_blocks(scope):
    from app.services.source_search import load_source_scope
    return load_source_scope(scope)[0]



def test_serialized_byte_cap(client,material,monkeypatch):
    import app.services.source_context as svc
    monkeypatch.setattr(svc,'MAX_SERIALIZED_BYTES',100)
    s,_=material
    r=client.get('/source-context',params={'q':'consent','source_id':s['id']})
    assert r.status_code==413


def test_pdf_context_retains_unsearchable_pages_and_page_citations(client):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject
    writer=PdfWriter()
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    p=writer.add_blank_page(width=200,height=200)
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 150 Td (consent before replacement) Tj ET');p[NameObject('/Contents')]=writer._add_object(stream)
    p=writer.add_blank_page(width=200,height=200)
    image=DecodedStreamObject();image.set_data(bytes([255,0,0]));image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),NameObject('/Width'):NumberObject(1),NameObject('/Height'):NumberObject(1),NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im0'):writer._add_object(image)})})
    stream=DecodedStreamObject();stream.set_data(b'q 20 0 0 20 10 10 cm /Im0 Do Q');p[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO();writer.write(output)
    source,_=upload(client,output.getvalue(),'context.pdf')
    package=context(client,source['id'],'consent')
    assert package['sources'][0]['image_only_pages']==[2]
    assert package['sources'][0]['no_text_pages']==[2]
    assert package['evidence'][0]['page_start']==1
    assert any('not interpreted' in note for note in package['sources'][0]['limitations'])
    assert verify_snapshot(package)



def test_missing_original_prevents_citation_reuse(client,material):
    s,_=material
    source=next(x for x in db.sources if x['id']==s['id'])
    Path(source['file_path']).unlink()
    p=context(client,s['id'])
    assert p['evidence'] and p['state']=='insufficient_evidence'
    assert not verify_snapshot(p)
    with pytest.raises(ValueError):validate_citations(p,[])
