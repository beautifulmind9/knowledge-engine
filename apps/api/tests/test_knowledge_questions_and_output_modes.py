from app.models.workshop import WorkshopPrepareRequest
from app.services import workshop
from app.services.output_modes import MODES
from app.services.workshop import _workshop_relevance


def _asset(**overrides):
    base = {
        "id": "asset_1",
        "asset_type": "principle",
        "title": "A useful idea",
        "what_it_says": "Use evidence-grounded knowledge when making a decision.",
        "why_it_matters": "It keeps the answer traceable.",
        "source_id": "source_1",
        "chunk_id": "chunk_1",
        "chapter_or_section": "Chapter 3: Simple",
        "evidence": "Use evidence-grounded knowledge.",
        "keywords": ["evidence", "decision"],
        "confidence_score": 4,
    }
    base.update(overrides)
    return base


def test_expanded_workshop_modes_are_registered():
    expected = {
        "knowledge_answer",
        "research_synthesis",
        "social_content",
        "action_plan",
        "presentation",
    }
    assert expected <= set(MODES)
    assert "LinkedIn post" in MODES["social_content"]["formats"]
    assert "Short-form video script" in MODES["social_content"]["formats"]


def test_output_format_is_part_of_workshop_request():
    payload = WorkshopPrepareRequest(
        situation="Turn this idea into a useful post.",
        goal="Create grounded content.",
        output_type="social_content",
        output_format="LinkedIn post",
    )
    assert payload.output_format == "LinkedIn post"


def test_knowledge_question_can_target_asset_type():
    payload = WorkshopPrepareRequest(
        situation="What concepts appear in this source?",
        goal="Show me the concepts.",
        output_type="knowledge_answer",
    )
    concept_score, concept_terms = _workshop_relevance(
        _asset(asset_type="concept"), payload
    )
    principle_score, _ = _workshop_relevance(
        _asset(asset_type="principle"), payload
    )

    assert concept_score > principle_score
    assert "concepts" in concept_terms


def test_knowledge_question_can_use_chapter_or_section_provenance():
    payload = WorkshopPrepareRequest(
        situation="What did Chapter 3 Simple teach?",
        goal="Explain the chapter.",
        output_type="knowledge_answer",
    )
    matching_score, matching_terms = _workshop_relevance(
        _asset(chapter_or_section="Chapter 3: Simple"), payload
    )
    other_score, _ = _workshop_relevance(
        _asset(chapter_or_section="Chapter 7: Stories"), payload
    )

    assert matching_score > other_score
    assert "simple" in matching_terms


def test_broad_knowledge_answer_falls_back_to_representative_assets(monkeypatch):
    monkeypatch.setattr(workshop, "list_knowledge_assets", lambda source_id=None: [_asset()])
    payload = WorkshopPrepareRequest(
        situation="What does this source teach?",
        goal="What does this source teach?",
        output_type="knowledge_answer",
    )

    items = workshop._retrieve_raw_assets(payload)

    assert len(items) == 1
    assert items[0]["id"] == "asset_1"
    assert items[0]["relevance_score"] >= 1
