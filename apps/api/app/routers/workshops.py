from fastapi import APIRouter

router = APIRouter(prefix="/workshops", tags=["workshops"])


@router.post("")
def create_workshop():
    return {
        "message": "create workshop placeholder"
    }
