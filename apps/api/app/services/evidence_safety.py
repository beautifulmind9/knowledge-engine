"""Deterministic source closure and application resource budgets.

These limits bound work, not relevance or research sufficiency. Rejection never
truncates member evidence, modifies a saved output or makes a provider call.
"""
import json

from fastapi import HTTPException


# Conservative MVP operating budgets, not claims about a provider's token window.
# The reviewed 1,000-record probe is the largest measured consolidation workload.
MAX_CANDIDATE_ASSETS = 1000
MAX_CANDIDATE_BYTES = 4 * 1024 * 1024
MAX_WORKSHOP_REQUEST_BYTES = 64 * 1024
MAX_PREPARED_BYTES = 512 * 1024
MAX_PREPARED_UNITS = 20  # The existing WorkshopPrepareRequest.limit maximum.
MAX_PROVIDER_CONTEXT_BYTES = 256 * 1024

INTERPRETATION_FIELDS = (
    'asset_type', 'title', 'what_it_says', 'why_it_matters', 'keywords',
    'condition', 'action', 'rationale', 'consequence', 'prevention',
    'what_happened', 'transferable_lesson', 'concept_demonstrated',
    'adaptation_notes', 'steps', 'components', 'how_to_apply',
    'when_to_use', 'when_not_to_use', 'tradeoffs',
)


def _reject_scope():
    raise HTTPException(409, 'Evidence provenance does not match the selected materials. '
                        'Update the knowledge preview or review the material. No provider request was sent.',
                        headers={'X-KE-Interruption-Category': 'evidence_scope_invalid'})


def check_json_budget(value, limit, *, message):
    """Count the same UTF-8 JSON representation without keeping an extra body."""
    size = 0
    for part in json.JSONEncoder(ensure_ascii=False).iterencode(value):
        size += len(part.encode('utf-8'))
        if size > limit:
            raise HTTPException(413, message + ' No evidence was truncated and no provider request was sent.',
                                headers={'X-KE-Interruption-Category': 'evidence_capacity_exceeded'})
    return size


def check_candidate_budget(items):
    if len(items) > MAX_CANDIDATE_ASSETS:
        reject_candidate_capacity()
    check_json_budget(items, MAX_CANDIDATE_BYTES,
                      message='This knowledge scope is too large. Choose fewer materials or a smaller scope.')


def reject_candidate_capacity():
    raise HTTPException(413, 'This knowledge scope exceeds the measured application capacity. '
                        'Choose fewer materials or a smaller scope. No evidence was truncated '
                        'and no provider request was sent.',
                        headers={'X-KE-Interruption-Category': 'evidence_capacity_exceeded'})


def request_scope(payload):
    """None means unrestricted; an empty library scope means no sources allowed."""
    selected = set(payload.source_ids) if payload.source_ids else None
    if payload.library_id:
        from app.db.mock_data import libraries, sources
        if not any(library['id'] == payload.library_id for library in libraries):
            _reject_scope()
        library_sources = {source['id'] for source in sources if source.get('library_id') == payload.library_id}
        if selected is not None and not selected <= library_sources:
            _reject_scope()
        selected = library_sources if selected is None else selected
    return selected


def _known_chunk_manifests(source_ids):
    from app.db.mock_data import sources
    from app.services.chunk_manifest import valid_manifest
    return {source['id']: set(source['chunk_manifest']['chunk_ids']) for source in sources
            if source['id'] in source_ids and valid_manifest(source['id'], source.get('chunk_manifest'))}


def require_available_sources(source_ids):
    from app.db.mock_data import sources
    if not set(source_ids) <= {source['id'] for source in sources}:
        _reject_scope()


def validate_raw_sources(items, allowed=None):
    identities = {}
    manifests = _known_chunk_manifests({item.get('source_id') for item in items})
    for item in items:
        source = item.get('source_id')
        if not source or (allowed is not None and source not in allowed):
            _reject_scope()
        aid = item.get('id')
        identity = (source, item.get('chunk_id'))
        if source in manifests and item.get('chunk_id') not in manifests[source]:
            _reject_scope()
        if aid and aid in identities and identities[aid] != identity:
            _reject_scope()
        if aid:
            identities[aid] = identity


def validate_units(units, allowed=None, *, context=None, selected_assets=()):
    """Check every representation; never trust only group-level source_ids.

    Historical single-source context can use the existing unambiguous fallback.
    Ambiguous multi-source member provenance cannot authorize new generation.
    This validates identity, not whether a quotation entails an interpretation.
    """
    owners = {}
    material_ids = set()
    manifests = _known_chunk_manifests({sid for unit in units
                                       for sid in [*(unit.get('source_ids') or []),
                                                   (unit.get('canonical_asset') or {}).get('source_id'),
                                                   *(row.get('source_id') for row in unit.get('evidence_trail', []))]})
    for index, unit in enumerate(units):
        canonical = unit.get('canonical_asset') or {}
        cid = canonical.get('id') or unit.get('asset_id')
        if not cid:
            _reject_scope()
        members = list(unit.get('asset_ids') or [cid])
        if len(members) != len(set(members)) or cid not in members:
            _reject_scope()
        if unit.get('asset_id') and unit['asset_id'] != cid:
            _reject_scope()
        declared = set(unit.get('source_ids') or [])
        own_source = canonical.get('source_id') or unit.get('source_id')
        trail = unit.get('evidence_trail') or []
        known = declared | {row['source_id'] for row in trail if row.get('source_id')}
        if own_source:
            known.add(own_source)
        if not known or (allowed is not None and not known <= allowed):
            _reject_scope()
        if canonical.get('source_id') and unit.get('source_id') and canonical['source_id'] != unit['source_id']:
            _reject_scope()
        for row in trail:
            if not row.get('source_id') or (row.get('asset_id') and row['asset_id'] not in members):
                _reject_scope()
            if not row.get('asset_id') and len(known) != 1:
                _reject_scope()
        member_sources = set()
        for aid in members:
            rows = [row for row in trail if row.get('asset_id') == aid]
            sources = {row['source_id'] for row in rows}
            if aid == cid and own_source:
                sources.add(own_source)
            if not sources and any(row.get('asset_id') for row in trail):
                _reject_scope()
            if not sources and len(known) == 1:
                sources = set(known)
            chunks = {row['chunk_id'] for row in rows if row.get('chunk_id')}
            if aid == cid and canonical.get('chunk_id'):
                chunks.add(canonical['chunk_id'])
            if len(sources) != 1 or len(chunks) > 1:
                _reject_scope()
            source = next(iter(sources))
            if source in manifests and not chunks <= manifests[source]:
                _reject_scope()
            if unit.get('chunk_ids') and not chunks <= set(unit['chunk_ids']):
                _reject_scope()
            if aid in owners:
                _reject_scope()
            owners[aid] = index
            member_sources.update(sources)
        if declared and declared != member_sources:
            _reject_scope()
        material_ids.update(member_sources)

    if not set(selected_assets) <= set(owners):
        raise HTTPException(409, 'Some selected ideas are missing from this preview. '
                            'Choose fewer ideas or update the knowledge preview. No provider request was sent.',
                            headers={'X-KE-Interruption-Category': 'selected_evidence_missing'})

    def check_context(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'source_id', 'source_ids'}:
                    ids = set(item if isinstance(item, list) else [item])
                    if not ids <= material_ids:
                        _reject_scope()
                elif key in {'asset_id', 'asset_ids'}:
                    ids = set(item if isinstance(item, list) else [item])
                    if not ids <= set(owners):
                        _reject_scope()
                else:
                    check_context(item)
        elif isinstance(value, list):
            for item in value:
                check_context(item)
    check_context(context or {})
    return material_ids


def validate_preparation(prepared, payload):
    check_json_budget(payload.model_dump(mode='json'), MAX_WORKSHOP_REQUEST_BYTES,
                      message='This request is too large. Shorten the request or attached instructions.')
    check_json_budget(prepared, MAX_PREPARED_BYTES,
                      message='This evidence preview is too large. Choose fewer materials or ideas.')
    if len(prepared['knowledge_units']) > MAX_PREPARED_UNITS:
        raise HTTPException(413, 'This evidence snapshot exceeds the existing preview limit. '
                            'Prepare a smaller scope. No evidence was truncated and no provider request was sent.',
                            headers={'X-KE-Interruption-Category': 'evidence_capacity_exceeded'})
    allowed = request_scope(payload)
    pinned = (prepared.get('evidence_base') or {}).get('selected_source_ids')
    if pinned is not None:
        allowed = set(pinned) if allowed is None else allowed & set(pinned)
    return validate_units(prepared['knowledge_units'], allowed, context=prepared.get('synthesis_context'),
                          selected_assets=payload.asset_ids)


def check_provider_context(payload, schema):
    # Use the gateway's actual schema adapter, not a token-count approximation.
    from app.services.ai_gateway import _gemini_response_schema
    response_format = {'type': 'text', 'mime_type': 'application/json', 'schema': _gemini_response_schema(schema)}
    schema_bytes = len(json.dumps(response_format).encode('utf-8'))
    check_json_budget(payload, MAX_PROVIDER_CONTEXT_BYTES - schema_bytes,
                      message='The complete generation context is too large. Choose fewer materials or ideas, '
                              'or shorten the request or revision.')
