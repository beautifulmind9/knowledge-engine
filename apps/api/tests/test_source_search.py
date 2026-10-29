import hashlib
import json
from pathlib import Path
import socket

import pytest
from app.db import mock_data as db
from app.services import ai_gateway
from app.services.source_search import _passages

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def no_generation(monkeypatch):
    def deny(*a,**k):raise AssertionError('Source search must not dispatch AI')
    monkeypatch.setattr(ai_gateway,'generate',deny)


def upload(client,text,name='source.md',library=None,process=True):
    lib=library or client.post('/libraries',json={'name':'Synthetic source search'}).json()
    source=client.post('/sources',json={'library_id':lib['id'],'title':name}).json()
    response=client.post(f"/sources/{source['id']}/upload",files={'file':(name,text,'application/octet-stream')})
    assert response.status_code==200,response.text
    if process:
        response=client.post(f"/sources/{source['id']}/process")
        assert response.status_code==200,response.text
    return source,lib


def search(client,q,sid=None,**kw):
    return client.get('/source-search',params={'q':q,**({'source_id':sid} if sid else {}),**kw})


@pytest.fixture
def frozen(client):
    text=(ROOT/'acceptance/extraction_quality_2026-10-17/source.md').read_text()
    assert hashlib.sha256(text.encode()).hexdigest()=='93afffd120832c93694a2e854e4a8dd444e0d1f83bc05d812ab7d49390485de8'
    return upload(client,text)[0],text


@pytest.mark.parametrize('query,expected',[
    ('consent inspect replace parts discard irreversible damage','Consent to inspect is not consent to replace parts'),
    ('intake ticket preferred name arrival time next station','It records a ticket number'),
    ('accepted items completed inspections repairs completed referrals categories separate','Keep the categories separate.'),
])
def test_known_omissions_with_zero_assets(client,frozen,query,expected):
    source,text=frozen
    result=search(client,query,source['id']).json()
    assert any(expected in b['text'] for b in result['items'])
    assert not db.knowledge_assets and not db.extraction_jobs
    assert result['coverage'][0]['status']=='indexed_text'
    for b in result['items']:
        assert b['source_id']==source['id']
        assert text[b['start_char']:b['end_char']]==b['text']
        assert b['text_sha256']==hashlib.sha256(text.encode()).hexdigest()


def test_unmapped_paraphrase_is_preserved_failure(client,frozen):
    source,_=frozen
    r=search(client,'How is informed assent delimited before disassembly?',source['id']).json()
    assert not any('Consent to inspect is not consent' in b['text'] for b in r['items'])
    assert 'Lexical' in r['limitations'][0]


def test_source_and_library_isolation(client):
    a,al=upload(client,'# A\n\nrepair ticket one')
    b,bl=upload(client,'# B\n\nrepair ticket two')
    assert {x['source_id'] for x in search(client,'repair',a['id']).json()['items']}=={a['id']}
    assert {x['source_id'] for x in search(client,'repair',library_id=bl['id']).json()['items']}=={b['id']}
    assert search(client,'repair',a['id'],library_id=bl['id']).status_code==404
    assert search(client,'repair','missing').status_code==404


def test_bounds_determinism_dedup_and_syntax(client,frozen):
    s,_=frozen
    a=search(client,'repair OR * NEAR() --',s['id'],limit=3).json()
    b=search(client,'repair OR * NEAR() --',s['id'],limit=3).json()
    assert a==b and len(a['items'])<=3
    assert len({x['passage_id'] for x in a['items']})==len(a['items'])
    assert search(client,'repair',s['id'],limit=11).status_code==422
    assert search(client,'x'*2001,s['id']).status_code==422
    assert search(client,'lunar isotope spectroscopy',s['id']).json()['items']==[]


def test_no_stale_index_on_change(client):
    s,_=upload(client,'# Old\n\nrepair ticket original')
    a=search(client,'ticket',s['id']).json()
    source=next(x for x in db.sources if x['id']==s['id'])
    Path(source['extracted_text_path']).write_text('# Updated\n\nrepair ticket replacement')
    b=search(client,'ticket',s['id']).json()
    assert a['items'][0]['source_version']!=b['items'][0]['source_version']
    assert b['items'][0]['text']=='repair ticket replacement'
    db.sources.remove(source)
    assert search(client,'ticket',s['id']).status_code==404


def test_preserved_not_read_and_missing_text(client):
    s,_=upload(client,'preserved words',process=False)
    r=search(client,'words',s['id']).json()
    assert r['items']==[] and r['coverage'][0]['status']=='preserved_not_indexed'
    assert r['coverage'][0]['original_available']
    source=next(x for x in db.sources if x['id']==s['id'])
    Path(source['file_path']).unlink()
    assert search(client,'words',s['id']).json()['coverage'][0]['status']=='uncertain_extraction'


def test_heading_without_blank_line_and_neighbor_context(client):
    s,_=upload(client,'# One\nfirst observation\n\nsecond qualification\n\nthird detail\n# Two\nother text')
    r=search(client,'second',s['id'],neighbors=True).json()['items'][0]
    assert r['section']=='One'
    assert {x['text'] for x in r['neighbors']}=={'first observation','third detail'}
    assert all(x['section']=='One' for x in r['neighbors'])


def test_pdf_unindexed_page_and_verified_page_mapping(client):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,NumberObject,DecodedStreamObject
    w=PdfWriter();font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')});ref=w._add_object(font)
    p=w.add_blank_page(width=200,height=200)
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):ref})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 150 Td (consent before replacement) Tj ET');p[NameObject('/Contents')]=w._add_object(stream)
    p=w.add_blank_page(width=200,height=200)
    image=DecodedStreamObject();image.set_data(bytes([255,0,0]));image.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),NameObject('/Width'):NumberObject(1),NameObject('/Height'):NumberObject(1),NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
    p[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im0'):w._add_object(image)})})
    stream=DecodedStreamObject();stream.set_data(b'q 20 0 0 20 10 10 cm /Im0 Do Q');p[NameObject('/Contents')]=w._add_object(stream)
    out=io.BytesIO();w.write(out)
    s,_=upload(client,out.getvalue(),'synthetic.pdf')
    result=search(client,'consent',s['id']).json()
    assert result['coverage'][0]['no_text_pages']==[2]
    assert result['coverage'][0]['image_only_pages']==[2]
    assert result['coverage'][0]['page_mapping']=='verified_text_alignment'
    assert result['items'][0]['page_start']==1


def test_search_preserves_extraction_first_state(client,knowledge):
    before=json.dumps([db.sources,db.extraction_jobs,db.knowledge_assets,db.outputs,db.usage],sort_keys=True)
    assert search(client,'practice',knowledge['source_id']).json()['items']
    assert json.dumps([db.sources,db.extraction_jobs,db.knowledge_assets,db.outputs,db.usage],sort_keys=True)==before


def test_long_passages_are_exact_bounded_slices():
    text='# Heading\n\n'+' '.join('word'+str(i) for i in range(600))
    bs=_passages({'id':'synthetic','title':'Synthetic'},text)
    assert len(bs)==3 and all(len(b['text'].split())==200 for b in bs)
    assert all(text[b['start_char']:b['end_char']]==b['text'] for b in bs)



def test_real_process_restart(tmp_path):
    import os,subprocess,sys
    script = r"""
import json,sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.services import ai_gateway
def deny(*a,**k):raise AssertionError('No AI')
ai_gateway.generate=deny
record=Path(sys.argv[2])
with TestClient(app) as c:
 if sys.argv[1]=='create':
  lib=c.post('/libraries',json={'name':'Restart synthetic'}).json()
  s=c.post('/sources',json={'library_id':lib['id'],'title':'Restart'}).json()
  assert c.post('/sources/'+s['id']+'/upload',files={'file':('source.md','# One\n\nconsent before replacement','text/markdown')}).status_code==200
  assert c.post('/sources/'+s['id']+'/process').status_code==200
  result=c.get('/source-search',params={'q':'consent','source_id':s['id']}).json()
  assert result['count']==1
  record.write_text(json.dumps({'source':s['id'],'result':result}))
 else:
  old=json.loads(record.read_text())
  result=c.get('/source-search',params={'q':'consent','source_id':old['source']}).json()
  assert result==old['result']
"""
    env=dict(os.environ,KNOWLEDGE_ENGINE_STORAGE=str(tmp_path/'storage'),PYTHONDONTWRITEBYTECODE='1')
    for name in ('GEMINI_API_KEY','KNOWLEDGE_ENGINE_DATABASE_URL'):env.pop(name,None)
    for action in ('create','search'):
        result=subprocess.run([sys.executable,'-c',script,action,str(tmp_path/'result.json')],cwd=ROOT/'apps/api',env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr


def test_frozen_benchmark_characterization(client):
    import os,math,statistics
    f=json.loads((ROOT/'experiments/source_first/fixture.json').read_text())
    ids={}
    for source in f['sources']:
        text=(ROOT/'experiments/source_first'/source['path']).read_text() if 'path' in source else source['text']
        ids[source['id']]=upload(client,text,source['id']+'.md')[0]['id']
    rows=[]
    for q in f['queries']:
        response=client.get('/source-search',params=[('q',q['query']),('limit',10)]+[('source_id',ids[x]) for x in q['scope']])
        assert response.status_code==200,response.text
        result=response.json()
        hits=[any(b['source_id']==ids[g['source_id']] and b['start_char']<=g['start'] and b['end_char']>=g['end'] for g in q['relevant']) for b in result['items']]
        n=len(q['relevant'])
        recall=sum(any(b['source_id']==ids[g['source_id']] and b['start_char']<=g['start'] and b['end_char']>=g['end'] for b in result['items']) for g in q['relevant'])/n if n else None
        ideal=sum(1/math.log2(i+2) for i in range(min(n,10)))
        rows.append({'id':q['id'],'kind':q['kind'],'recall_at_10':recall,'ndcg_at_10':sum(h/math.log2(i+2) for i,h in enumerate(hits))/ideal if ideal else None,'count':result['count'],'passages':result['items']})
    assert not db.knowledge_assets and not db.extraction_jobs
    target=os.environ.get('KE_SOURCE_SEARCH_REPORT')
    if target:
        Path(target).write_text(json.dumps({'queries':rows,'mean_recall_at_10':statistics.mean(x['recall_at_10'] for x in rows if x['recall_at_10'] is not None),'mean_ndcg_at_10':statistics.mean(x['ndcg_at_10'] for x in rows if x['ndcg_at_10'] is not None)},indent=2))



def test_no_duplicate_context_across_ranked_results(client,frozen):
    s,_=frozen
    items=search(client,'consent repair',s['id'],neighbors=True).json()['items']
    ids=[b['passage_id'] for b in items]+[n['passage_id'] for b in items for n in b['neighbors']]
    assert len(ids)==len(set(ids))


def test_search_refuses_oversized_source_without_partial_success(client):
    s,_=upload(client,'# Heading\n\n'+'a'*16001)
    assert search(client,'a',s['id']).status_code==413



def test_outside_storage_artifacts_are_not_searchable(client,tmp_path):
    s,_=upload(client,'# Source\n\noriginal permitted text')
    outside=tmp_path/'unrelated.txt';outside.write_text('synthetic private unrelated text')
    record=next(x for x in db.sources if x['id']==s['id'])
    record['extracted_text_path']=str(outside)
    result=search(client,'unrelated',s['id']).json()
    assert result['items']==[]
    assert result['coverage'][0]['status']=='preserved_not_indexed'
