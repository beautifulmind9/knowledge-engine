#!/usr/bin/env python3
"""Measure synthetic offline retrieval workloads; never opens a provider.

The figures describe one local Python process and tracemalloc-visible allocations.
They are development evidence, not production SLOs or hosted PostgreSQL benchmarks.
"""
import argparse
import gc
import json
import os
from pathlib import Path
import resource
import tempfile
import time
import tracemalloc


ROOT = Path(__file__).resolve().parents[1]


def measured(operation):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    outcome = "ok"
    result = None
    try:
        result = operation()
    except Exception as error:  # Report the public outcome without source content.
        outcome = f"{type(error).__name__}:{getattr(error, 'status_code', '')}"
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return outcome, result, round(elapsed, 6), peak


def _rss_bytes():
    """Return current Linux worker RSS without reading source or provider data."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _peak_rss_bytes():
    # Linux reports ru_maxrss in KiB. This script is Linux-only operational tooling.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def run(selected_workloads=None):
    process_started = time.perf_counter()
    rss_at_start = _rss_bytes()
    with tempfile.TemporaryDirectory(prefix="ke-phase-e-") as storage:
        os.environ["KNOWLEDGE_ENGINE_STORAGE"] = storage
        os.environ["KNOWLEDGE_ENGINE_PERSISTENCE_MODE"] = "local"
        for name in ("GEMINI_API_KEY", "GEMINI_FREE_TIER_CONFIRMED",
                     "KNOWLEDGE_ENGINE_DATABASE_URL", "SUPABASE_URL", "SUPABASE_SECRET_KEY"):
            os.environ.pop(name, None)

        import sys
        sys.path.insert(0, str(ROOT / "apps/api"))
        from pydantic import TypeAdapter
        from app.db import mock_data as db
        from app.models.knowledge_asset import KnowledgeAsset
        from app.models.workshop import WorkshopPrepareRequest
        from app.services import knowledge_extraction as retrieval, workshop

        adapter = TypeAdapter(KnowledgeAsset)

        def install(asset_count, source_count, library_count, *, duplicate=False, evidence_bytes=80):
            libraries = [{"id": f"library_{index}", "name": f"Library {index}"}
                         for index in range(library_count)]
            sources = [{"id": f"source_{index}", "title": f"Synthetic source {index}",
                        "library_id": libraries[index % library_count]["id"]}
                       for index in range(source_count)]
            assets = []
            for index in range(asset_count):
                identity = "shared" if duplicate else str(index)
                item = adapter.validate_python({
                    "asset_type": "principle", "id": f"asset_{index}",
                    "source_id": sources[index % source_count]["id"],
                    "chunk_id": f"chunk_{index}",
                    "title": f"Capacity concept {identity}",
                    "what_it_says": f"Capacity evidence contribution {identity}.",
                    "evidence": "capacity " + ("x" * max(1, evidence_bytes - 9)),
                    "keywords": ["capacity", f"term{identity}"], "confidence_score": 4,
                }).model_dump(mode="json")
                assets.append(item)
            db.libraries[:] = libraries
            db.sources[:] = sources
            db.knowledge_assets[:] = assets
            db.extraction_jobs.clear()
            db.outputs.clear()
            return libraries, sources, assets

        workloads = [
            ("small", 50, 5, 2, False, 80),
            ("typical", 250, 25, 3, False, 80),
            ("source_heavy", 50, 1000, 10, False, 80),
            ("large_distinct", 1000, 100, 5, False, 80),
            ("adversarial_duplicates", 1000, 100, 5, True, 80),
            ("oversized_count", 1001, 100, 1, False, 80),
            ("oversized_bytes", 128, 16, 1, False, 35000),
        ]
        if selected_workloads:
            known = {workload[0] for workload in workloads}
            unknown = sorted(set(selected_workloads) - known)
            if unknown:
                raise ValueError(f"Unknown workload(s): {', '.join(unknown)}")
            workloads = [workload for workload in workloads if workload[0] in selected_workloads]
        # Exclude one-time imports/cache initialization from workload comparisons.
        warm_libraries, warm_sources, _ = install(2, 1, 1)
        retrieval.search_consolidated_knowledge_assets(
            "capacity", library_id=warm_libraries[0]["id"], limit=20)
        workshop.prepare_workshop(WorkshopPrepareRequest(
            situation="Evaluate capacity evidence.", goal="Use capacity evidence.",
            source_ids=[warm_sources[0]["id"]], output_type="research_synthesis", limit=20))

        report = []
        for name, asset_count, source_count, library_count, duplicate, evidence_bytes in workloads:
            libraries, sources, assets = install(
                asset_count, source_count, library_count,
                duplicate=duplicate, evidence_bytes=evidence_bytes)
            serialized_candidates = len(json.dumps(assets, ensure_ascii=False).encode("utf-8"))
            try:
                full_groups = retrieval.consolidate_knowledge_assets(assets)
                consolidated_group_count = len(full_groups)
                consolidated_json_bytes = len(json.dumps(full_groups, ensure_ascii=False).encode("utf-8"))
            except Exception:
                consolidated_group_count = None
                consolidated_json_bytes = None

            def find_all_libraries():
                groups = []
                for library in libraries:
                    groups.extend(retrieval.search_consolidated_knowledge_assets(
                        "capacity", library_id=library["id"], limit=20))
                return groups

            find_outcome, find_result, find_seconds, find_peak = measured(find_all_libraries)

            payload = WorkshopPrepareRequest(
                situation="Evaluate capacity evidence.", goal="Use capacity evidence.",
                source_ids=[source["id"] for source in sources],
                output_type="research_synthesis", limit=20)
            workshop_outcome, prepared, workshop_seconds, workshop_peak = measured(
                lambda: workshop.prepare_workshop(payload))

            report.append({
                "workload": name,
                "asset_count": asset_count,
                "source_count": source_count,
                "library_count": library_count,
                "candidate_json_bytes": serialized_candidates,
                "full_consolidated_group_count": consolidated_group_count,
                "full_consolidated_json_bytes": consolidated_json_bytes,
                "find": {"outcome": find_outcome, "seconds": find_seconds,
                         "peak_tracemalloc_bytes": find_peak,
                         "returned_group_count": len(find_result) if find_result is not None else None},
                "workshop": {"outcome": workshop_outcome, "seconds": workshop_seconds,
                             "peak_tracemalloc_bytes": workshop_peak,
                             "returned_group_count": len(prepared["knowledge_units"]) if prepared else None,
                             "prepared_json_bytes": (len(json.dumps(prepared, ensure_ascii=False).encode("utf-8"))
                                                     if prepared else None)},
            })
        return {
            "kind": "synthetic offline measurement; Python allocations and Linux worker RSS",
            "provider_calls": 0,
            "process": {
                "rss_at_start_bytes": rss_at_start,
                "rss_at_end_bytes": _rss_bytes(),
                "peak_rss_bytes": _peak_rss_bytes(),
                "elapsed_seconds": round(time.perf_counter() - process_started, 6),
            },
            "workloads": report,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workload", action="append", dest="workloads",
                        help="Measure only this named workload; repeat to select several.")
    args = parser.parse_args()
    content = json.dumps(run(args.workloads), indent=2) + "\n"
    if args.output:
        args.output.write_text(content)
    else:
        print(content, end="")
