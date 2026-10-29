import json
from pathlib import Path
import sqlite3
import socket

import pytest
from prototype import SourceIndex, passages
from evaluate import load_fixture, run


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a,**k):raise AssertionError('No network permitted')
    monkeypatch.setattr(socket,'socket',deny)
    monkeypatch.setattr(socket,'create_connection',deny)


@pytest.fixture
def index():
    f,texts=load_fixture();i=SourceIndex(aliases=f['aliases'])
    for sid,text in texts.items():i.put(sid,text)
    yield i
    i.close()


def test_frozen_labels_and_source_integrity():
    f,texts=load_fixture()
    assert len(f['queries'])==26 and len(f['omission_probe_ids'])==6
    assert len(texts)==3


def test_exact_original_locations_and_ke_word_ranges():
    f,texts=load_fixture()
    for sid,text in texts.items():
        bs=passages(sid,text)
        assert all(text[b['start_char']:b['end_char']]==b['text'] for b in bs)
        assert all(b['end_word_index']-b['start_word_index']==b['word_count'] for b in bs)
        assert all(a['end_char']<=b['start_char'] for a,b in zip(bs,bs[1:]))


def test_no_assets_or_application_imports(index):
    assert index.retrieve('intake ticket',['repair'])['ranked']
    code=(Path(__file__).parent/'prototype.py').read_text()
    assert 'from app' not in code and 'google' not in code
    assert not index.db.execute("SELECT name FROM sqlite_master WHERE name LIKE '%asset%'").fetchall()


def test_query_and_candidate_dedup(index):
    a=index.retrieve('intake ticket',['repair'],'fusion')
    b=index.retrieve('intake ticket '*4,['repair'],'fusion')
    assert a['ranked']==b['ranked']
    assert len(a['blocks'])==len({b['id'] for b in a['blocks']})
    assert len(index.plan('"job card" job card '*4,True))<=4


def test_real_neighbor_expansion(index):
    a=index.retrieve('diagnosis card',['repair'],'context',max_blocks=12)
    assert any(b['id'] not in a['ranked'][:4] for b in a['blocks'])
    assert len({b['id'] for b in a['blocks']})==len(a['blocks'])


def test_budget_does_not_truncate_passages(index):
    result=index.retrieve('intake ticket',['repair'],'context',max_blocks=2,max_words=80)
    assert result['word_count']<=80 and len(result['blocks'])<=2
    assert result['excluded']
    for b in result['blocks']:
        assert b in index.blocks(['repair'])


def test_cache_copy_and_repeat(index):
    a=index.retrieve('repair',['repair']);a['blocks'].clear()
    b=index.retrieve('repair',['repair'])
    assert b['cache_hit'] and b['blocks']


@pytest.mark.parametrize('change',['text','add','remove','parser','scope','aliases','budget','mode'])
def test_cache_invalidation(index,change):
    a=index.retrieve('repair',['repair'])
    assert index.retrieve('repair',['repair'])['cache_hit']
    kwargs={}
    if change=='text':index.put('repair','# Changed\n\nrepair replacement only')
    if change=='add':index.put('new','repair competing source')
    if change=='remove':index.remove('noise')
    if change=='parser':
        text=index.db.execute('SELECT text FROM sources WHERE id="repair"').fetchone()[0]
        index.put('repair',text,parser='parser-v2')
    if change=='scope':kwargs['scope']=['alpha']
    if change=='aliases':index.aliases['repair']='workshop'
    if change=='budget':kwargs['max_words']=50
    if change=='mode':kwargs['mode']='fusion'
    b=index.retrieve('repair',kwargs.pop('scope',['repair']),**kwargs)
    assert not b['cache_hit']


def test_delete_denies_stale_scope(index):
    index.retrieve('repair',['repair']);index.remove('repair')
    with pytest.raises(ValueError):index.retrieve('repair',['repair'])


def test_scope_is_enforced_before_search_and_context(index):
    for mode in ('bm25','expanded','fusion','context'):
        r=index.retrieve('intake ticket',['alpha'],mode,'cross')
        assert all(b['source_id']=='alpha' for b in r['blocks'])


def test_fts_syntax_is_data(index):
    r=index.retrieve('" OR * NEAR() -- intake; DROP TABLE sources',['repair'])
    assert len(index.blocks(['repair']))>0


def test_restart_and_refuse_foreign_database(tmp_path):
    p=tmp_path/'index.sqlite';i=SourceIndex(p);i.put('s','# A\n\nrepair ticket')
    before=i.retrieve('ticket',['s']);i.close()
    i=SourceIndex(p);after=i.retrieve('ticket',['s']);i.close()
    assert before['context_hash']==after['context_hash'] and before['ranked']==after['ranked']
    foreign=tmp_path/'app.sqlite';c=sqlite3.connect(foreign);c.execute('CREATE TABLE state(x)');c.close()
    raw=foreign.read_bytes()
    with pytest.raises(sqlite3.OperationalError):SourceIndex(foreign)
    assert foreign.read_bytes()==raw


def test_evaluation_is_characterization_not_quality_assertion():
    result=run()
    assert len(result['queries'])==26 and result['provider_calls']==0
    assert all(item['modes'][mode]['metrics']['location_integrity'] for item in result['queries'] for mode in item['modes'])


@pytest.mark.parametrize('format',['docx','html','pdf'])
def test_existing_multimodal_parser_limits_are_explicit(format):
    from multimodal_probe import run
    result=run()['fixtures'][format]
    assert result['caption_retained']
    if format=='docx':
        assert result['original_unchanged'] and result['embedded_images_in_original']==1
        assert result['table_values_headers_footnote_retained']
        assert not result['image_to_caption_relationship_in_text_contract']
    elif format=='html':
        assert result['image_data_in_original'] and not result['image_alt_retained']
    else:
        assert result['original_unchanged_after_annotation']
        assert result['image_only_page_retained_in_original'] and result['image_only_page_silently_absent_from_text']


def test_cache_context_versions_change_and_old_results_remain_snapshots(index):
    old=index.retrieve('intake ticket',['repair'])
    old_versions={b['source_version'] for b in old['blocks']}
    index.put('repair','# New\n\nintake ticket: updated decision authority.')
    new=index.retrieve('intake ticket',['repair'])
    assert old_versions.isdisjoint({b['source_version'] for b in new['blocks']})
    assert old['context_hash']!=new['context_hash']
    assert len(old['blocks'])>len(new['blocks'])
