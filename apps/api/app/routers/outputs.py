from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from app.db.mock_data import outputs
from app.models.output import RevisionRequest, ManualOutputRequest
from app.services.outputs import get_output, save_output, revise_output, compare_outputs, export_markdown
from app.services.knowledge_extraction import persist_state
from app.services.workshop import prepare_workshop
from app.services.output_modes import MODES

router=APIRouter(prefix="/outputs", tags=["outputs"])

@router.get("/modes")
def modes():
    return {"items":[{"id":k,**v} for k,v in MODES.items()]}

@router.get("")
def list_outputs(output_type:str|None=None, source_id:str|None=None, created_after:datetime|None=None):
    items=[o for o in outputs if (not output_type or o["output_type"]==output_type)
        and (not source_id or source_id in o["source_ids"])
        and (not created_after or datetime.fromisoformat(o["created_at"]).timestamp() >= created_after.timestamp())]
    keys=("id","title","output_type","source_ids","created_at","root_output_id","parent_output_id","version")
    return {"items":[{k:o[k] for k in keys} for o in sorted(items,key=lambda o:o["created_at"],reverse=True)],"count":len(items)}

@router.post("")
def import_output(payload:ManualOutputRequest):
    prepared=prepare_workshop(payload.brief)
    if payload.output.output_type != payload.brief.output_type:
        raise ValueError("Output type must match the brief.")
    return save_output({"output":payload.output.model_dump(mode="json"), "brief":prepared["brief"],
                       "knowledge_snapshot":prepared["knowledge_units"], "provider":"manual"})

@router.get("/{output_id}")
def read_output(output_id:str):
    return get_output(output_id)

@router.post("/{output_id}/revise")
def revise(output_id:str, payload:RevisionRequest):
    return revise_output(output_id,payload)

@router.get("/{output_id}/history")
def history(output_id:str):
    root=get_output(output_id)["root_output_id"]
    return {"items":sorted([o for o in outputs if o["root_output_id"]==root],key=lambda o:o["version"])}

@router.get("/{output_id}/quality")
def review_quality(output_id:str):
    from app.services.output_modes import quality_report
    output = get_output(output_id)
    return quality_report(output, output["brief"], output["knowledge_snapshot"])

@router.get("/{output_id}/compare/{other_id}")
def compare(output_id:str,other_id:str):
    return compare_outputs(output_id,other_id)

@router.get("/{output_id}/export",response_class=PlainTextResponse)
def export(output_id:str):
    return PlainTextResponse(export_markdown(get_output(output_id)),media_type="text/markdown",
        headers={"Content-Disposition":f'attachment; filename="{output_id}.md"'})

@router.delete("/{output_id}")
def delete(output_id:str, entire_history:bool=False):
    output=get_output(output_id)
    if not entire_history:
        raise HTTPException(409,"Deletion removes this output's entire revision history. Set entire_history=true to confirm.")
    deleted=[o["id"] for o in outputs if o["root_output_id"]==output["root_output_id"]]
    outputs[:]=[o for o in outputs if o["id"] not in deleted]
    persist_state()
    return {"deleted_ids":deleted}
