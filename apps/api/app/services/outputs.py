from copy import deepcopy
from datetime import datetime, timezone
from difflib import unified_diff
from app.db.mock_data import outputs, create_id
from app.models.output import OutputRecord
from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.knowledge_extraction import persist_state
from app.services.output_modes import quality_report


def get_output(output_id):
    output = next((o for o in outputs if o["id"] == output_id), None)
    if output is None:
        raise ValueError("Output not found.")
    return output


def save_output(result, parent=None, instruction=None):
    output = result["output"]
    snapshot = deepcopy(result["knowledge_snapshot"])
    available = {g["canonical_asset"]["id"] for g in snapshot}
    applied = [a["asset_id"] for a in output["applied_knowledge"]]
    if not applied or not set(applied) <= available:
        raise ValueError("Applied assets must come from the supplied knowledge snapshot.")
    # Keep all retrieved context for reproducible revisions; source_ids describes material use.
    source_ids = sorted({sid for g in snapshot if g["canonical_asset"]["id"] in applied
                         for sid in g.get("source_ids", [g["canonical_asset"]["source_id"]])})
    now = datetime.now(timezone.utc)
    oid = create_id("output")
    root = parent["root_output_id"] if parent else oid
    version = max((o["version"] for o in outputs if o["root_output_id"] == root), default=0)+1
    record = OutputRecord(**output, id=oid, brief=deepcopy(result["brief"]), source_ids=source_ids,
        applied_asset_ids=applied, knowledge_snapshot=snapshot, provider=result["provider"], model=result.get("model"),
        created_at=now, updated_at=now, root_output_id=root, parent_output_id=parent["id"] if parent else None,
        version=version, revision_instruction=instruction,
        generation_metadata={"model_response_id":result.get("model_response_id"), "quality":quality_report(output)})
    data=record.model_dump(mode="json")
    outputs.append(data)
    persist_state()
    return deepcopy(data)


def revise_output(output_id, request):
    parent = get_output(output_id)
    if request.content is not None:
        result = {"brief":parent["brief"], "knowledge_snapshot":parent["knowledge_snapshot"], "provider":"manual", "model":None,
                  "output":{key:deepcopy(parent[key]) for key in ("title","output_type","content","applied_knowledge","design_choices")}}
        result["output"].update(content=request.content, title=request.title or parent["title"],
            design_choices=request.design_choices if request.design_choices is not None else deepcopy(parent["design_choices"]))
        result["output"]["design_choices"].append("Manual revision: " + request.instruction + ". Source attribution requires review.")
    else:
        from app.services.workshop_generation import generate_workshop_output
        payload=WorkshopGenerateRequest(**{k:v for k,v in parent["brief"].items() if k != "retrieval_query"})
        from app.services.workshop import synthesis_context
        prepared={"brief":parent["brief"], "knowledge_units":parent["knowledge_snapshot"], "knowledge_unit_count":len(parent["knowledge_snapshot"]),
                  "synthesis_context":synthesis_context(parent["knowledge_snapshot"])}
        result=generate_workshop_output(payload, prepared=prepared, revision={"instruction":request.instruction, "previous_output":parent["content"]})
    return save_output(result, parent, request.instruction)


def compare_outputs(left_id, right_id):
    left,right=get_output(left_id),get_output(right_id)
    if left["root_output_id"] != right["root_output_id"]:
        raise ValueError("Compare versions belonging to the same output history.")
    return {"from":left_id,"to":right_id,"content_diff":"\n".join(unified_diff(left["content"].splitlines(),right["content"].splitlines(),fromfile=f"v{left['version']}",tofile=f"v{right['version']}",lineterm="")),
            "changed_fields":[k for k in ("title","content","applied_knowledge","design_choices") if left[k]!=right[k]]}


def export_markdown(output):
    lines=["# "+output["title"], "", output["content"], "", "## Applied knowledge"]
    for ref in output["applied_knowledge"]:
        lines.append(f"- {ref['asset_id']}: {ref['usage_note']}")
    lines += ["", "## Design choices"]+["- "+v for v in output["design_choices"]]
    lines += ["", "## Provenance", f"Output: {output['id']} | Version: {output['version']} | Created: {output['created_at']}",
              "Sources: "+", ".join(output["source_ids"]), "Provider: "+output["provider"], "", "## Brief"]
    lines += [f"- {k}: {v}" for k,v in output["brief"].items()]
    for group in output["knowledge_snapshot"]:
        if group["canonical_asset"]["id"] in output["applied_asset_ids"]:
            lines += ["", "### "+group["canonical_asset"]["title"]]
            for trail in group.get("evidence_trail", []):
                lines += [f"- Source {trail['source_id']}; chunk {trail['chunk_id']}; asset {trail['asset_id']}"]
    return "\n".join(lines)+"\n"
