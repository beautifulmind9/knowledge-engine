from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.db.mock_data import extraction_jobs, knowledge_assets, libraries, sources
from app.db.persistence import save_state
from app.services.source_structure import annotate_pdf_assets_with_outline_from_evidence


router = APIRouter(prefix="/sources", tags=["sources"])


def _find_source(source_id: str):
    return next((source for source in sources if source.get("id") == source_id), None)


@router.post("/{source_id}/refine-asset-sections")
def refine_asset_sections(source_id: str):
    """Refine PDF asset section labels from exact stored evidence.

    This is a local deterministic metadata repair. It does not change source
    text, chunks, extracted knowledge claims, or make any AI/provider call.
    """
    source = _find_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.get("file_type") != ".pdf":
        raise HTTPException(status_code=400, detail="Evidence-based section refinement is available only for PDF sources.")

    file_path = source.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Uploaded PDF file not found on disk.")

    assets = [asset for asset in knowledge_assets if asset.get("source_id") == source_id]
    before = {asset.get("id"): asset.get("chapter_or_section") for asset in assets}

    try:
        summary = annotate_pdf_assets_with_outline_from_evidence(file_path, assets)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Asset section refinement failed: {error}") from error

    changed_ids = [
        asset.get("id")
        for asset in assets
        if before.get(asset.get("id")) != asset.get("chapter_or_section")
    ]

    source["asset_section_refinement_status"] = "pdf_evidence_refined"
    source["asset_section_refinement_count"] = len(changed_ids)
    save_state(libraries, sources, extraction_jobs, knowledge_assets)

    return {
        "source_id": source_id,
        **summary,
        "updated_asset_count": len(changed_ids),
        "structure_status": source["asset_section_refinement_status"],
        "message": "Asset sections refined from exact PDF evidence without changing knowledge or making an AI call.",
    }
