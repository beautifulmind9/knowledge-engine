#!/usr/bin/env python3
"""Replay synthetic relevance cases locally; never opens a provider or hosted store.

Run: .venv/bin/python scripts/diagnose_relevance.py [--output /tmp/report.json]
Add --diagnostics for ID/term/score explanations, or --code-root for an offline
archive of the baseline code. Fixture data always comes from this script's repo.
Only the tracked synthetic fixture is supported. This tool never reads live state.
"""
import argparse
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(code_root=ROOT, include_diagnostics=False):
    # Set isolation before importing application modules (which initialize storage).
    with tempfile.TemporaryDirectory(prefix='ke-relevance-') as storage:
        os.environ['KNOWLEDGE_ENGINE_STORAGE'] = storage
        os.environ['KNOWLEDGE_ENGINE_PERSISTENCE_MODE'] = 'local'
        for name in ('KNOWLEDGE_ENGINE_DATABASE_URL', 'KNOWLEDGE_ENGINE_WORKSPACE_KEY',
                     'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'GEMINI_API_KEY',
                     'GEMINI_FREE_TIER_CONFIRMED'):
            os.environ.pop(name, None)
        sys.path.insert(0, str(Path(code_root) / 'apps/api'))
        from pydantic import TypeAdapter
        from app.models.knowledge_asset import KnowledgeAsset
        from app.models.workshop import WorkshopPrepareRequest
        from app.db import mock_data as db
        from app.services import knowledge_extraction as retrieval, workshop
        fixture = json.loads((ROOT / 'apps/api/tests/fixtures/relevance/research_cases.json').read_text())
        db.sources[:] = fixture['sources']
        db.libraries[:] = [{'id': lid, 'name': lid} for lid in sorted({s['library_id'] for s in fixture['sources']} | {'excluded_empty'})]
        db.knowledge_assets[:] = [TypeAdapter(KnowledgeAsset).validate_python(a['asset']).model_dump(mode='json') for a in fixture['assets']]
        from app.services.text_chunking import save_chunks
        from app.services.chunk_manifest import manifest_from_chunks
        # Real synthetic lifecycle artifacts distinguish incomplete preparation
        # from a prepared material with no matching knowledge. No provider runs.
        for source in db.sources:
            preparation = fixture.get('preparation', {}).get(source['id'])
            if preparation is None:
                continue
            path = Path(storage) / (source['id'] + '.md')
            path.write_text('Synthetic preparation material only.')
            chunks = [{'id': f"chunk_{source['id']}_{index:03}", 'source_id': source['id'],
                       'chunk_index': index, 'text': 'Synthetic preparation material only.'}
                      for index in range(1, preparation['total_parts'] + 1)]
            source.update(file_path=str(path), chunks_path=save_chunks(source['id'], chunks),
                          chunk_manifest=manifest_from_chunks(source['id'], chunks))
            # Bind this synthetic lifecycle's assets to its real synthetic
            # chunk IDs. The retained historical fixture/report is not rewritten.
            for item in db.knowledge_assets:
                if item['source_id'] == source['id']:
                    item['chunk_id'] = chunks[0]['id']
            db.extraction_jobs.extend({'id': 'synthetic_' + chunk['id'], 'source_id': source['id'],
                                       'chunk_id': chunk['id'], 'status': 'completed'}
                                      for chunk in chunks[:preparation['completed_parts']])
        supports_diagnostics = 'diagnostics' in inspect.signature(retrieval.search_consolidated_knowledge_assets).parameters
        results = []
        for case in fixture['cases']:
            groups = []
            traces = []
            scopes = ([{'source_id': sid} for sid in case['source_ids']] if 'source_ids' in case else
                      [{'library_id': library} for library in case['library_ids']])
            for scope in scopes:
                options = {}
                if supports_diagnostics and include_diagnostics:
                    from app.services.retrieval_diagnostics import RetrievalDiagnostics
                    trace = RetrievalDiagnostics()
                    options['diagnostics'] = trace
                groups += retrieval.search_consolidated_knowledge_assets(case['query'], limit=case['limit'], **scope, **options)
                if supports_diagnostics and include_diagnostics:
                    traces.append(trace.as_dict())
            groups.sort(key=lambda group: group.get('relevance_score', 0), reverse=True)
            groups = groups[:case['limit']]
            ids = [group['canonical_asset']['id'] for group in groups]
            member_ids = {aid for group in groups for aid in group['asset_ids']}
            direct_retained = sum(aid in member_ids for aid in case['direct_ids'])
            incidental_positions = [index for index, group in enumerate(groups) if set(group['asset_ids']) & set(case['incidental_ids'])]
            direct_positions = [index for index, group in enumerate(groups) if set(group['asset_ids']) & set(case['direct_ids'])]
            selected = case.get('source_ids', [s['id'] for s in fixture['sources'] if s['library_id'] in case['library_ids']])
            request = WorkshopPrepareRequest(situation=case['query'], goal=case['query'], source_ids=selected,
                                             library_id=case['library_ids'][0] if not selected and len(case['library_ids']) == 1 else None,
                                             output_type='research_synthesis', limit=min(case['limit'], 20))
            prepared = workshop.prepare_workshop(request)
            workshop_groups = prepared['knowledge_units']
            workshop_members = {aid for group in workshop_groups for aid in group['asset_ids']}
            results.append({'case_id': case['id'], 'expectation': case.get('expectation', 'lexical_acceptance'), 'search_ids': ids,
                            'search_members': [group['asset_ids'] for group in groups],
                            'direct_retained': direct_retained, 'direct_expected': len(case['direct_ids']),
                            'direct_before_incidental': not incidental_positions or bool(direct_positions) and max(direct_positions) < min(incidental_positions),
                            'workshop_source_ids': sorted({sid for group in prepared['knowledge_units'] for sid in group['source_ids']}),
                            'selected_source_ids': selected,
                            'workshop_ids': [group['canonical_asset']['id'] for group in workshop_groups],
                            'workshop_members': [group['asset_ids'] for group in workshop_groups],
                            'workshop_direct_retained': sum(aid in workshop_members for aid in case['direct_ids']),
                            'source_preparation': [{k: row[k] for k in ('source_id', 'prepared_sections', 'total_sections', 'relevant_idea_count')}
                                                   for row in prepared.get('source_coverage', [])],
                            'scope_preserved': all(sid in selected for group in prepared['knowledge_units'] for sid in group['source_ids']),
                            **({'diagnostics': traces} if supports_diagnostics and include_diagnostics else {})})
        return {'fixture': 'research_cases.json', 'kind': 'synthetic lexical evaluation; labels are not runtime evidence judgments', 'cases': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--code-root', type=Path, default=ROOT)
    parser.add_argument('--diagnostics', action='store_true')
    args = parser.parse_args()
    report = run(args.code_root, args.diagnostics)
    content = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(content)
    else:
        print(content, end='')
