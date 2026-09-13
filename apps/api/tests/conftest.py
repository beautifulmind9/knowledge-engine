import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['KNOWLEDGE_ENGINE_STORAGE']=tempfile.mkdtemp(prefix='ke-tests-')
os.environ.pop('GEMINI_API_KEY',None)
os.environ.pop('GEMINI_FREE_TIER_CONFIRMED',None)
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import mock_data as db
from app.services.knowledge_extraction import persist_state

@pytest.fixture(autouse=True)
def clean_state():
    for records in (db.libraries,db.sources,db.extraction_jobs,db.knowledge_assets,db.outputs):
        records.clear()
    db.usage.clear()
    persist_state()
    yield

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

@pytest.fixture
def source(client):
    library=client.post('/libraries',json={'name':'Test research'}).json()
    source=client.post('/sources',json={'library_id':library['id'],'title':'Original facilitator notes','author':'Synthetic fixture'}).json()
    content='# Focus\nUse practice breaks to help participants retain learning.\nUse specific goals and practical activities.'
    assert client.post(f"/sources/{source['id']}/upload",files={'file':('notes.md',content,'text/markdown')}).status_code==200
    assert client.post(f"/sources/{source['id']}/process").status_code==200
    chunk=client.get(f"/sources/{source['id']}/chunks").json()['items'][0]
    return source,chunk

@pytest.fixture
def asset(source):
    s,c=source
    return {'asset_type':'principle','source_id':s['id'],'chunk_id':c['id'],'title':'Practice breaks',
            'what_it_says':'Use practice breaks to help participants retain learning.',
            'evidence':'Use practice breaks to help participants retain learning.',
            'keywords':['practice','breaks','learning'],'confidence_score':4}

@pytest.fixture
def knowledge(client,source,asset):
    s,c=source
    job=client.post('/knowledge-extractions',json={'source_id':s['id'],'chunk_id':c['id']}).json()['job']
    r=client.post(f"/knowledge-extractions/{job['id']}/results",json={'assets':[asset]})
    assert r.status_code==200,r.text
    return r.json()['assets'][0]
