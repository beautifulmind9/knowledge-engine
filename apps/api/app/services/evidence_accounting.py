"""Resolve citation identity from immutable snapshots, without expanding group support."""


def canonical_id(unit):
    return (unit.get('canonical_asset') or {}).get('id') or unit.get('asset_id')


def reference_maps(units):
    canonical_by_asset = {}
    sources_by_asset = {}
    for unit in units:
        canonical = unit.get('canonical_asset') or {}
        cid = canonical_id(unit)
        members = {cid, unit.get('asset_id'), *(unit.get('asset_ids') or [])}
        trail = unit.get('evidence_trail') or []
        members.update(item.get('asset_id') for item in trail)
        for aid in members - {None}:
            if cid:
                canonical_by_asset[aid] = cid
            exact = {item['source_id'] for item in trail
                     if item.get('asset_id') == aid and item.get('source_id')}
            if not exact and aid in {cid, unit.get('asset_id')}:
                sid = canonical.get('source_id') or unit.get('source_id')
                if sid:
                    exact = {sid}
            # Legacy trails may lack member IDs. A single source is unambiguous;
            # a multi-source group is context, not proof of each member's origin.
            if not exact:
                known = {item['source_id'] for item in trail if item.get('source_id')}
                known.update(unit.get('source_ids') or [])
                if len(known) == 1:
                    exact = known
            sources_by_asset.setdefault(aid, set()).update(exact)
    return canonical_by_asset, sources_by_asset


def cited_sources(units, references):
    _, sources = reference_maps(units)
    return sorted({sid for aid in references for sid in sources.get(aid, set())})


def output_references(output):
    retained = output.get('generation_metadata', {}).get('citation_asset_ids')
    if retained is not None:
        return set(retained)
    sections = output.get('reasoning_sections')
    if sections:
        return {aid for section in sections for aid in section.get('supporting_asset_ids', [])}
    return {ref['asset_id'] for ref in output.get('applied_knowledge', [])}
