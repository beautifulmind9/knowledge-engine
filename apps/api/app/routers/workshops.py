from fastapi import APIRouter

from app.models.workshop import WorkshopPrepareRequest
from app.services.workshop import prepare_workshop

router = APIRouter(prefix="/workshops", tags=["workshops"])


@router.get("")
def read_workshop_capabilities():
    return {
        "status": "ready",
        "capabilities": [
            "accept a real situation and goal",
            "retrieve relevant consolidated knowledge",
            "organize knowledge by asset type",
            "preserve source and chunk provenance",
        ],
        "next_step": "output generation",
    }


@router.post("/prepare")
def prepare_workshop_knowledge(payload: WorkshopPrepareRequest):
    return prepare_workshop(payload)
