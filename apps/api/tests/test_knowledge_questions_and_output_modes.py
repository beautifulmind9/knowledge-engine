from pathlib import Path

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


def test_prepare_preserves_output_format(monkeypatch):
    monkeypatch.setattr(workshop, "_retrieve_raw_assets", lambda payload: [_asset()])
    payload = WorkshopPrepareRequest(
        situation="Turn this idea into a useful post.",
        goal="Create grounded content.",
        output_type="social_content",
        output_format="LinkedIn post",
    )

    prepared = workshop.prepare_workshop(payload)

    assert prepared["brief"]["output_format"] == "LinkedIn post"


def test_browser_forwards_format_as_field_not_retrieval_constraint():
    repo_root = Path(__file__).resolve().parents[3]
    javascript = (repo_root / "apps" / "web" / "enhancements.js").read_text(
        encoding="utf-8"
    )

    assert "payload.output_format = selectedFormat" in javascript
    assert "lines.push(`${prefix}${value}`)" not in javascript


def test_all_knowledge_shortcuts_answer_in_knowledge_view_before_workshop_handoff():
    repo_root = Path(__file__).resolve().parents[3]
    javascript = (repo_root / "apps" / "web" / "enhancements.js").read_text(
        encoding="utf-8"
    )

    questions = [
        "What does this source teach?",
        "What concepts appear in this source?",
        "What problems does this source help solve?",
        "What did this chapter teach?",
        "What examples support this idea?",
        "What decision rules can I apply?",
    ]
    for question in questions:
        assert f'"{question}"' in javascript

    assert "generateKnowledgeAnswer(question, quickButton)" in javascript
    assert 'fetch("/workshops/generate"' in javascript
    assert 'output_type: "knowledge_answer"' in javascript
    assert "save: false" in javascript
    assert 'button("Open in Workshop"' in javascript
    assert "Answers appear here using one explicit Gemini request" in javascript
    assert 'makeElement("button", "Ask knowledge", "primary")' in javascript


def test_knowledge_answer_enhancement_has_its_own_rendering_helpers():
    repo_root = Path(__file__).resolve().parents[3]
    javascript = (repo_root / "apps" / "web" / "enhancements.js").read_text(
        encoding="utf-8"
    )

    # enhancements.js is a separate ES module and cannot rely on module-scoped
    # helper functions from app.js.
    assert "function detail(title, ...nodes)" in javascript
    assert "function list(items)" in javascript
    assert "function actions(...nodes)" in javascript
    assert "function button(text, action, className" in javascript


def test_context_dependent_knowledge_shortcuts_require_scope_before_gemini():
    repo_root = Path(__file__).resolve().parents[3]
    javascript = (repo_root / "apps" / "web" / "enhancements.js").read_text(
        encoding="utf-8"
    )

    assert 'const CHAPTER_QUESTION = "What did this chapter teach?"' in javascript
    assert 'const IDEA_EXAMPLES_QUESTION = "What examples support this idea?"' in javascript
    assert '#ke-chapter-scope' in javascript
    assert '#ke-idea-scope' in javascript
    assert "if (!validateKnowledgeQuestionScope(question)) return;" in javascript
    assert "Choose a chapter or section first" in javascript
    assert "Name the idea first" in javascript
    assert "No Gemini request was used." in javascript


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
