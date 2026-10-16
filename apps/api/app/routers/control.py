import io
import json
from shutil import copyfileobj
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.db.mock_data import libraries, sources, extraction_jobs, knowledge_assets, outputs
from app.db.persistence import STORAGE_ROOT, StateMutationConflict
from app.persistence.factory import get_artifact_store
from app.persistence.artifact_paths import contained_locator, archive_entry
from app.services.knowledge_extraction import find_source, persist_state
from app.services.ai_gateway import status, resume_usage, current_usage_state

router=APIRouter(tags=["data control"])
_artifact_store = get_artifact_store()

@router.get("/usage")
def usage_status():
    return status()

@router.post("/usage/resume")
def resume():
    return resume_usage()

@router.get("/data/integrity")
def integrity():
    source_ids={s["id"] for s in sources}
    library_ids={l["id"] for l in libraries}
    output_ids={o["id"] for o in outputs}
    issues=[]
    for source in sources:
        if source["library_id"] not in library_ids:
            issues.append({"id":source["id"],"problem":"orphaned library"})
        for key in ("file_path","chunks_path","extracted_text_path"):
            if source.get(key) and _artifact_store.status(Path(source[key])) != "artifact":
                issues.append({"id":source["id"],"problem":"missing "+key})
    for item in extraction_jobs+knowledge_assets:
        if item["source_id"] not in source_ids:
            issues.append({"id":item["id"],"problem":"orphaned source"})
    for output in outputs:
        if output.get("parent_output_id") and output["parent_output_id"] not in output_ids:
            issues.append({"id":output["id"],"problem":"missing parent output"})
        snapshot_ids={g["canonical_asset"]["id"] for g in output["knowledge_snapshot"]}
        if not set(output["applied_asset_ids"]) <= snapshot_ids:
            issues.append({"id":output["id"],"problem":"broken output provenance"})
    return {"ok":not issues,"issues":issues}

@router.get("/data/export")
def export_data():
    # Includes private source files: never link this endpoint from a public demo.
    buffer=io.BytesIO()
    source_copy=json.loads(json.dumps(sources))
    with ZipFile(buffer,"w",ZIP_DEFLATED) as archive:
        for source in source_copy:
            for key in ("file_path","extracted_text_path","chunks_path"):
                value=source.get(key)
                if value and _artifact_store.status(Path(value)) == "artifact":
                    try:
                        path=contained_locator(_artifact_store, Path(value), STORAGE_ROOT)
                    except ValueError:
                        raise HTTPException(409,"A legacy file is outside storage. Move it into storage before export.")
                    relative="storage/"+str(path.relative_to(STORAGE_ROOT))
                    # Match ZipFile.write metadata and buffered copying through the store.
                    entry = archive_entry(_artifact_store, path, relative)
                    if entry.is_dir():
                        archive.mkdir(entry)
                    else:
                        entry.compress_type = archive.compression
                        with _artifact_store.open_binary_read(path) as artifact, archive.open(entry, "w") as target:
                            copyfileobj(artifact, target, 1024 * 8)
                    source[key]=relative
        archive.writestr("storage/state.json",json.dumps(dict(libraries=libraries,sources=source_copy,
            extraction_jobs=extraction_jobs,knowledge_assets=knowledge_assets,outputs=outputs,
            usage=current_usage_state()),indent=2))
        archive.writestr("RESTORE.txt","Private backup. Stop the server. Extract storage into a NEW empty directory. Set KNOWLEDGE_ENGINE_STORAGE to that storage directory, then start the app. Never overwrite a live database.\n")
    return Response(buffer.getvalue(),media_type="application/zip",headers={"Content-Disposition":'attachment; filename="knowledge-engine-backup.zip"'})

@router.delete("/sources/{source_id}")
def delete_source(source_id:str,delete_outputs:bool=False):
    source=find_source(source_id)
    if not source:
        raise HTTPException(404,"Source not found.")
    affected_roots={o["root_output_id"] for o in outputs if any(source_id in g.get("source_ids",[g["canonical_asset"]["source_id"]]) for g in o["knowledge_snapshot"])}
    if affected_roots and not delete_outputs:
        raise HTTPException(409,"Saved output histories contain this source's knowledge. Set delete_outputs=true to delete those histories too, or keep the source.")
    paths=[]
    for key in ("file_path","extracted_text_path","chunks_path"):
        if source.get(key):
            try:
                path=contained_locator(_artifact_store, Path(source[key]), STORAGE_ROOT)
            except ValueError:
                raise HTTPException(409,"A legacy file is outside the private storage directory. Resolve its location before deletion.")
            paths.append(path)
    previous_outputs = list(outputs)
    previous_assets = list(knowledge_assets)
    previous_jobs = list(extraction_jobs)
    previous_sources = list(sources)
    outputs[:]=[o for o in outputs if o["root_output_id"] not in affected_roots]
    knowledge_assets[:]=[a for a in knowledge_assets if a["source_id"]!=source_id]
    extraction_jobs[:]=[j for j in extraction_jobs if j["source_id"]!=source_id]
    sources.remove(source)
    try:
        # Persist the logical deletion before removing required source artifacts.
        # A stale-state conflict can then restore the latest source record without
        # leaving it pointed at files that this request already removed.
        persist_state()
    except Exception as error:
        if isinstance(error, StateMutationConflict):
            raise
        # Keep the live API state usable when the save fails. No artifact has
        # been touched, so the source remains usable if persistence rejects it.
        outputs[:] = previous_outputs
        knowledge_assets[:] = previous_assets
        extraction_jobs[:] = previous_jobs
        sources[:] = previous_sources
        raise

    cleanup_pending = False
    for path in paths:
        try:
            _artifact_store.remove(path)
        except Exception:
            # The source deletion is already durable. Keep it deleted rather
            # than restoring a record whose required artifacts may be gone.
            # A leftover private artifact is safer and can be cleaned later.
            cleanup_pending = True
    result = {"deleted_source_id":source_id,"deleted_output_histories":len(affected_roots)}
    if cleanup_pending:
        result["artifact_cleanup_pending"] = True
    return result

@router.delete("/libraries/{library_id}")
def delete_library(library_id:str):
    library=next((l for l in libraries if l["id"]==library_id),None)
    if not library:
        raise HTTPException(404,"Library not found.")
    if any(s["library_id"]==library_id for s in sources):
        raise HTTPException(409,"Delete this library's sources first.")
    libraries.remove(library)
    persist_state()
    return {"deleted_library_id":library_id}
