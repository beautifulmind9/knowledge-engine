"""Offline checks for Phase 2 projections, authority markers and reconciliation."""
from contextvars import copy_context
from copy import deepcopy
import json

import pytest

from app.db.request_state import ProjectionList, view
from app.persistence.phase2 import active, compact, rebase_projection, MARKER
from app.persistence.partitions import PartitionVersionError
from app.persistence.reconciliation import StateReconciliationConflict


def state():
    return {'sources':[{'id':'s','title':'Before','processing_status':'chunked','stopped_reason':None}],
            'extraction_jobs':[{'id':'j'}], 'knowledge_assets':[{'id':'asset','active':True}],
            'outputs':[{'id':'output','version':1}], 'libraries':[{'id':'l'}], 'partition':MARKER}


@pytest.mark.parametrize('marker',[None,{},True,{'version':1,'state':'active'},
                                    {'version':2,'state':'active','domains':['jobs']},
                                    {'version':3,'state':'active','domains':['jobs','source_lifecycle']}])
def test_malformed_or_wrong_domain_authority_fails_closed(marker):
    with pytest.raises(PartitionVersionError):active({'partition':marker})


def test_no_marker_remains_legacy_and_supported_marker_is_explicit():
    assert not active(None) and not active({})
    assert active({'partition':deepcopy(MARKER)})


def test_phase2_compaction_preserves_asset_output_library_authority():
    original=state();result=compact(original)
    assert 'extraction_jobs' not in result
    assert result['sources']==[{'id':'s','title':'Before'}]
    for key in ('knowledge_assets','outputs','libraries'):assert result[key]==original[key]
    assert original['sources'][0]['processing_status']=='chunked'


def test_request_local_list_serialization_and_mutations_do_not_leak():
    projection=ProjectionList('sources',[{'id':'global'}])
    def request():
        token=view.set({'sources':[{'id':'request'}]})
        try:
            projection.append({'id':'new'})
            assert json.loads(json.dumps(projection))==[{'id':'request'},{'id':'new'}]
            assert deepcopy(projection)==[{'id':'request'},{'id':'new'}]
            assert {'id':'request'} in projection
            projection.remove({'id':'request'})
            assert projection.copy()==[{'id':'new'}]
        finally:view.reset(token)
    copy_context().run(request)
    assert list(projection)==[{'id':'global'}]


def test_core_rebase_preserves_concurrent_narrow_fields_without_dual_writes():
    baseline=state();local=deepcopy(baseline);latest=deepcopy(baseline)
    local['libraries'][0]['name']='Edited'
    latest['sources'][0]['processing_status']='knowledge_interpreting'
    result=rebase_projection(baseline,local,latest)
    assert result['sources'][0]['processing_status']=='knowledge_interpreting'
    assert result['libraries'][0]['name']=='Edited'
    assert 'extraction_jobs' not in result


def test_overlapping_narrow_edits_fail_closed_when_reconciling_core():
    baseline=state();local=deepcopy(baseline);latest=deepcopy(baseline)
    local['sources'][0]['stopped_reason']='local';latest['sources'][0]['stopped_reason']='other'
    with pytest.raises(StateReconciliationConflict):rebase_projection(baseline,local,latest)


def test_rehydrated_legacy_state_keeps_historical_generations_fenced(monkeypatch):
    from app.db import mock_data as db
    from app.services import partition_authority as authority
    monkeypatch.setattr(authority,'PERSISTENCE_MODE','local')
    db.sources[:]=[{'id':'s','generation':2}]
    old={'id':'old','source_id':'s','chunk_id':'same','status':'failed','generation':1}
    current={'id':'new','source_id':'s','chunk_id':'same','status':'pending_ai','generation':2}
    db.extraction_jobs[:]=[old,current]
    assert authority.jobs('s')==[current]
    assert authority.jobs('s',history=True)==[old,current]
    with pytest.raises(ValueError,match='fenced'):authority.legacy_generation_guard(old)
    authority.legacy_generation_guard(current)


def test_legacy_failure_transition_rejects_historical_generation(monkeypatch):
    from app.db import mock_data as db
    from app.services import partition_authority as authority
    from app.services.knowledge_extraction import mark_extraction_job_failed
    monkeypatch.setattr(authority,'PERSISTENCE_MODE','local')
    db.sources[:]=[{'id':'s','generation':2}]
    historical={'id':'old','source_id':'s','chunk_id':'same','status':'completed','generation':1}
    db.extraction_jobs[:]=[historical]
    with pytest.raises(ValueError,match='fenced'):
        mark_extraction_job_failed('old','late failure',persist=False)
    assert historical['status']=='completed'


def test_scoped_projection_does_not_materialize_unneeded_asset_corpus():
    from app.db.request_state import LazyProjection
    class Unreadable:
        def __deepcopy__(self,memo):raise AssertionError('unnecessary corpus copy')
    assets=ProjectionList('knowledge_assets',[])
    token=view.set({'knowledge_assets':LazyProjection(Unreadable())})
    try:
        # Replacing the whole post-commit view also need not materialize its old cache.
        assets[:]=[{'id':'confirmed'}]
        assert list(assets)==[{'id':'confirmed'}]
    finally:view.reset(token)
