from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
def get_sources():
    return []


@router.post("")
def create_source():
    return {
        "message": "create source placeholder"
    }
