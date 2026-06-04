from fastapi import APIRouter

router = APIRouter(prefix="/libraries", tags=["libraries"])


@router.get("")
def get_libraries():
    return []


@router.post("")
def create_library():
    return {
        "message": "create library placeholder"
    }
