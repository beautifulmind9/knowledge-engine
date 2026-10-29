from fastapi import APIRouter, Query
from app.services.source_search import search_passages

router = APIRouter(tags=["source-search"])


@router.get("/source-search")
def source_search(q: str = Query(min_length=1, max_length=2000),
                  source_id: list[str] | None = Query(default=None),
                  library_id: str | None = None,
                  limit: int = Query(default=10, ge=1, le=10),
                  neighbors: bool = False):
    return search_passages(q, source_id, library_id, limit, neighbors)


@router.get("/source-context")
def source_context(q: str = Query(min_length=1, max_length=2000),
                   source_id: list[str] | None = Query(default=None), library_id: str | None = None,
                   strategy: str = Query(default="targeted", pattern="^(targeted|broad)$"),
                   max_passages: int | None = Query(default=None, ge=1, le=64),
                   max_words: int = Query(default=6000, ge=1, le=6000),
                   max_chars: int = Query(default=48000, ge=1, le=48000)):
    from app.services.source_context import build_source_context
    return build_source_context(q, source_id, library_id, strategy, max_passages, max_words, max_chars)


from app.models.source_answer import SourceAnswerRequest


@router.post("/experimental/source-answers")
def experimental_source_answer(payload: SourceAnswerRequest):
    from app.services.source_answer import answer_source
    return answer_source(payload)


@router.get("/experimental/source-answers/{record_id}")
def experimental_source_answer_record(record_id: str):
    from app.services.source_answer import read_source_answer
    return read_source_answer(record_id)


@router.delete("/experimental/source-answers/{record_id}")
def experimental_source_answer_delete(record_id: str):
    from app.services.source_answer import delete_source_answer
    return delete_source_answer(record_id)
