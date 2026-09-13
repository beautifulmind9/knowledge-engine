import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.db.mock_data import libraries, sources, extraction_jobs, knowledge_assets, outputs, usage
from app.db.persistence import STORAGE_ROOT
from app.services.knowledge_extraction import find_source, persist_state
from app.services.ai_gateway import status

router=APIRouter(tags=["data control"])

@router.get("/usage")
def usage_status():
    return status()

@router.post("/usage/resume")
def resume():
    usage.update(paused=False, reason=None)
    persist_state()
    return status()

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
            if source.get(key) and not Path(source[key]).is_file():
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
                if value and Path(value).is_file():
                    path=Path(value).resolve()
                    if not path.is_relative_to(STORAGE_ROOT):
                        raise HTTPException(409,"A legacy file is outside storage. Move it into storage before export.")
                    relative="storage/"+str(path.relative_to(STORAGE_ROOT))
                    archive.write(path,relative)
                    source[key]=relative
        archive.writestr("storage/state.json",json.dumps(dict(libraries=libraries,sources=source_copy,
            extraction_jobs=extraction_jobs,knowledge_assets=knowledge_assets,outputs=outputs,usage=usage),indent=2))
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
            path=Path(source[key]).resolve()
            if not path.is_relative_to(STORAGE_ROOT):
                raise HTTPException(409,"A legacy file is outside the private storage directory. Resolve its location before deletion.")
            paths.append(path)
    # File failures stop deletion before removing records; integrity audit identifies partial disk deletion.
    for path in paths:
        path.unlink(missing_ok=True)
    outputs[:]=[o for o in outputs if o["root_output_id"] not in affected_roots]
    knowledge_assets[:]=[a for a in knowledge_assets if a["source_id"]!=source_id]
    extraction_jobs[:]=[j for j in extraction_jobs if j["source_id"]!=source_id]
    sources.remove(source)
    persist_state()
    return {"deleted_source_id":source_id,"deleted_output_histories":len(affected_roots)}

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
