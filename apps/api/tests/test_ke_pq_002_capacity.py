"""Operating-budget rejection must be explicit, non-destructive and offline."""
from collections import OrderedDict
from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from app.db import mock_data as db
from app.services import evidence_safety as safety, knowledge_extraction as extraction
from app.services import prepared_evidence, workshop_generation
from test_ke_pq_002_integrity_review import asset, install, prepared, request, fake_provider


def test_candidate_limit_rejects_before_any_pairwise_comparison(monkeypatch):
    items = [asset(), asset('asset_b')]
    original = deepcopy(items)
    monkeypatch.setattr(safety, 'MAX_CANDIDATE_ASSETS', 1)
    monkeypatch.setattr(extraction, '_similarity_features', lambda *_: pytest.fail('comparison work started'))
    with pytest.raises(HTTPException) as error:
        extraction.consolidate_knowledge_assets(items)
    assert error.value.status_code == 413
    assert 'No evidence was truncated' in error.value.detail
    assert items == original


def test_candidate_byte_budget_counts_utf8_before_comparison(monkeypatch):
    items = [asset(evidence='A synthetic passage. ' + 'λ' * 200)]
    size = len(json.dumps(items, ensure_ascii=False).encode('utf-8'))
    monkeypatch.setattr(safety, 'MAX_CANDIDATE_BYTES', size - 1)
    monkeypatch.setattr(extraction, '_similarity_features', lambda *_: pytest.fail('comparison work started'))
    with pytest.raises(HTTPException) as error:
        extraction.consolidate_knowledge_assets(items)
    assert error.value.status_code == 413


def test_oversized_search_request_rejects_before_candidate_acquisition(monkeypatch):
    monkeypatch.setattr(extraction, 'list_knowledge_assets',
                        lambda **_: pytest.fail('candidate acquisition started'))
    with pytest.raises(HTTPException) as error:
        extraction.search_knowledge_assets('x' * (safety.MAX_WORKSHOP_REQUEST_BYTES + 1))
    assert error.value.status_code == 413


def test_oversized_workshop_request_rejects_before_candidate_acquisition(monkeypatch):
    from app.services import workshop
    payload = request().model_copy(update={'situation': 'x' * safety.MAX_WORKSHOP_REQUEST_BYTES})
    monkeypatch.setattr(workshop, '_retrieve_raw_assets',
                        lambda **_: pytest.fail('candidate acquisition started'))
    with pytest.raises(HTTPException) as error:
        workshop.prepare_workshop(payload)
    assert error.value.status_code == 413


def test_oversized_preparation_cannot_reach_provider_or_mutate_history(monkeypatch):
    install([asset()])
    snapshot = prepared([asset()])
    original = deepcopy(snapshot)
    calls = fake_provider(monkeypatch)
    monkeypatch.setattr(safety, 'MAX_PREPARED_BYTES', 40)
    with pytest.raises(HTTPException) as error:
        workshop_generation.generate_workshop_output(request(), prepared=snapshot)
    assert error.value.status_code == 413
    assert calls == [] and db.outputs == [] and snapshot == original


def test_actual_serialized_provider_budget_has_an_exact_inclusive_boundary(monkeypatch):
    from app.services.ai_gateway import _gemini_response_schema
    install([asset()])
    snapshot = prepared([asset()])
    calls = fake_provider(monkeypatch)
    workshop_generation.generate_workshop_output(request(), prepared=deepcopy(snapshot))
    _, payload, schema = calls[0]
    response_format = {'type': 'text', 'mime_type': 'application/json', 'schema': _gemini_response_schema(schema)}
    size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) + len(json.dumps(response_format).encode('utf-8'))
    monkeypatch.setattr(safety, 'MAX_PROVIDER_CONTEXT_BYTES', size)
    workshop_generation.generate_workshop_output(request(), prepared=deepcopy(snapshot))
    assert len(calls) == 2
    monkeypatch.setattr(safety, 'MAX_PROVIDER_CONTEXT_BYTES', size - 1)
    with pytest.raises(HTTPException) as error:
        workshop_generation.generate_workshop_output(request(), prepared=deepcopy(snapshot))
    assert error.value.status_code == 413 and len(calls) == 2


def test_revision_context_is_included_in_the_same_single_attempt_preflight(monkeypatch):
    install([asset()])
    snapshot = prepared([asset()])
    original = deepcopy(snapshot)
    calls = fake_provider(monkeypatch)
    with pytest.raises(HTTPException) as error:
        workshop_generation.generate_workshop_output(request(), prepared=snapshot, revision={
            'previous_output': 'x' * safety.MAX_PROVIDER_CONTEXT_BYTES, 'instruction': 'Clarify this artifact.'})
    assert error.value.status_code == 413
    assert calls == [] and db.outputs == []
    # No returned/generated text or saved parent is rewritten to fit the budget.
    assert snapshot == original


def test_preview_cache_is_bounded_by_bytes_and_eviction_remains_explicit(monkeypatch):
    install([asset()])
    snapshot = prepared([asset()])
    payload = request(interaction_revision=7)
    size = len(json.dumps(snapshot, ensure_ascii=False).encode('utf-8'))
    monkeypatch.setattr(prepared_evidence, '_snapshots', OrderedDict())
    monkeypatch.setattr(prepared_evidence, '_snapshot_sizes', {})
    monkeypatch.setattr(prepared_evidence, 'MAX_CACHED_EVIDENCE_BYTES', size + 1)
    first = prepared_evidence.remember_preparation(payload, snapshot)
    second = prepared_evidence.remember_preparation(payload, snapshot)
    assert len(prepared_evidence._snapshots) == 1
    with pytest.raises(HTTPException) as error:
        prepared_evidence.resolve_preparation(payload.model_copy(update={'prepared_snapshot_id': first['prepared_snapshot_id']}))
    assert error.value.status_code == 409
    resolved = prepared_evidence.resolve_preparation(payload.model_copy(update={'prepared_snapshot_id': second['prepared_snapshot_id']}))
    assert resolved['knowledge_units'] == snapshot['knowledge_units']
    assert db.outputs == []


def test_oversized_saved_revision_stops_before_synthesis_and_preserves_parent(monkeypatch):
    from app.services.outputs import revise_output
    from app.models.output import RevisionRequest
    install([asset()])
    snapshot = prepared([asset()])
    parent = {'id':'saved', 'brief':request().model_dump(), 'knowledge_snapshot':snapshot['knowledge_units']}
    db.outputs[:] = [parent]
    original = deepcopy(parent)
    calls = fake_provider(monkeypatch)
    monkeypatch.setattr(safety, 'MAX_PREPARED_BYTES', 10)
    monkeypatch.setattr('app.services.workshop.synthesis_context', lambda *_: pytest.fail('synthesis started before preflight'))
    with pytest.raises(HTTPException) as error:
        revise_output('saved', RevisionRequest(instruction='Clarify this output.'))
    assert error.value.status_code == 413
    assert calls == [] and db.outputs == [original]


def test_missing_saved_material_blocks_ai_revision_without_rewriting_history(monkeypatch):
    from app.services.outputs import revise_output
    from app.models.output import RevisionRequest
    install([asset()])
    snapshot = prepared([asset()])
    parent = {'id':'saved', 'brief':request().model_dump(), 'knowledge_snapshot':snapshot['knowledge_units']}
    db.outputs[:] = [deepcopy(parent)]
    db.sources.clear()
    calls = fake_provider(monkeypatch)
    with pytest.raises(HTTPException) as error:
        revise_output('saved', RevisionRequest(instruction='Clarify this output.'))
    assert error.value.status_code == 409
    assert calls == [] and db.outputs == [parent]


@pytest.mark.parametrize('operation', ['list', 'search'])
def test_indexed_capacity_failure_is_mapped_before_payload_materialization(monkeypatch, operation):
    from app.persistence.partitions import PartitionCapacityExceeded
    calls = []

    class OversizedAdapter:
        version = 3

        def active_assets(self, **kwargs):
            calls.append(('list', kwargs))
            raise PartitionCapacityExceeded(1001, 1024)

        def search_candidates(self, *args, **kwargs):
            calls.append(('search', kwargs))
            raise PartitionCapacityExceeded(1001, 1024)

    monkeypatch.setattr(extraction.authority, 'coordinator', lambda: OversizedAdapter())
    with pytest.raises(HTTPException) as error:
        if operation == 'list':
            extraction.list_knowledge_assets(source_ids=['source_a'])
        else:
            extraction.search_knowledge_assets('narratives', source_id='source_a')
    assert error.value.status_code == 413
    assert error.value.headers['X-KE-Interruption-Category'] == 'evidence_capacity_exceeded'
    assert calls == [(operation, {
        **({'source_ids': ['source_a'], 'chunk_id': None, 'asset_type': None}
           if operation == 'list' else {'source_ids': None, 'source_id': 'source_a', 'asset_type': None}),
        'max_items': safety.MAX_CANDIDATE_ASSETS,
        'max_bytes': safety.MAX_CANDIDATE_BYTES,
    })]


def test_indexed_list_rejects_result_that_grows_after_database_preflight(monkeypatch):
    """The application check closes separate READ COMMITTED statement snapshots."""
    item = asset()

    class ChangedAfterPreflightAdapter:
        version = 3

        def active_assets(self, **kwargs):
            assert kwargs['max_items'] == safety.MAX_CANDIDATE_ASSETS
            return [dict(item, id=f"asset_{index}")
                    for index in range(safety.MAX_CANDIDATE_ASSETS + 1)]

    monkeypatch.setattr(extraction.authority, 'coordinator', lambda: ChangedAfterPreflightAdapter())
    with pytest.raises(HTTPException) as error:
        extraction.list_knowledge_assets(source_ids=[item['source_id']])
    assert error.value.status_code == 413
    assert error.value.headers['X-KE-Interruption-Category'] == 'evidence_capacity_exceeded'
    assert 'No evidence was truncated' in error.value.detail
