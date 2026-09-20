import json
from types import SimpleNamespace

from app.models.workshop import WorkshopPrepareRequest
from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.output_modes import quality_report
from app.services.workshop import _meaningful_terms, _workshop_relevance, build_workshop_query
from app.services.workshop_generation import generate_workshop_output


def test_study_guide_retrieval_filters_generic_and_structural_terms():
    payload = WorkshopPrepareRequest(
        situation=(
            "I am preparing to facilitate workshops and want a study resource that helps me "
            "remember the practical principles for keeping participants engaged, managing "
            "session timing, designing useful practice, and handling questions."
        ),
        goal="Create a study guide I can use to learn and review the most useful facilitation principles from the source.",
        audience="A beginner facilitator with little formal workshop-design experience.",
        constraints=[
            "Include practical application, not just definitions",
            "Include review questions with answer or checking guidance",
            "Keep claims grounded in the selected source",
            "Do not invent facilitation frameworks that are not supported by the source",
        ],
        output_type="study_guide",
        source_ids=["source_1"],
    )

    query_terms = set(build_workshop_query(payload).split())
    assert "questions" in query_terms  # substantive in the situation
    assert not {"review", "answer", "checking", "guidance"} & query_terms
    assert not {"can", "do", "just", "little", "me", "not", "facilitation", "facilitator", "participants", "session"} & query_terms


def test_study_guide_relevance_prefers_requested_topics_over_facilitation_boilerplate():
    payload = WorkshopPrepareRequest(
        situation=(
            "Remember practical principles for keeping participants engaged, managing session timing, "
            "designing useful practice, and handling questions."
        ),
        goal="Create a useful study resource.",
        audience="A beginner facilitator.",
        constraints=["Include review questions with answer or checking guidance"],
        output_type="study_guide",
        source_ids=["source_1"],
    )

    def asset(title, what_it_says, keywords):
        return {
            "title": title,
            "what_it_says": what_it_says,
            "why_it_matters": None,
            "evidence": what_it_says,
            "keywords": keywords,
        }

    generic_score, _ = _workshop_relevance(
        asset(
            "Facilitation for participants",
            "A facilitator supports participants during a workshop session.",
            ["facilitation", "participants", "session"],
        ),
        payload,
    )
    timing_score, timing_terms = _workshop_relevance(
        asset(
            "Schedule safety net",
            "Protect time when the schedule is running late.",
            ["schedule", "time"],
        ),
        payload,
    )
    practice_score, practice_terms = _workshop_relevance(
        asset(
            "Exercise design",
            "Use an exercise so learners can apply the idea.",
            ["exercise", "application"],
        ),
        payload,
    )
    engagement_score, engagement_terms = _workshop_relevance(
        asset(
            "Recover attention",
            "Change the activity when attention drops.",
            ["attention"],
        ),
        payload,
    )

    assert timing_score > generic_score
    assert practice_score > generic_score
    assert engagement_score > generic_score
    assert "timing" in timing_terms
    assert {"practice", "practical"} & set(practice_terms)
    assert "engaged" in engagement_terms


def test_elapsed_minute_range_table_header_is_not_an_unparsed_agenda_line():
    output = {
        "title": "SOP workshop",
        "output_type": "workshop_plan",
        "content": """## Agenda
| Elapsed Minute Range | Activity |
| :--- | :--- |
| 0–15 min | Introduction |
| 15–30 min | Lecture |
| 30–50 min | Process Deconstruction |
| 50–75 min | Guided Practice |
| 75–90 min | Structured Q&A |
## Activities
Details here.
""",
        "applied_knowledge": [{"asset_id": "asset_1", "usage_note": "Used for timing."}],
        "design_choices": [],
    }

    report = quality_report(
        output,
        {"constraints": ["90 minutes total"]},
        [],
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unparsed_agenda_line" not in codes
    assert report["timing_checks"][0]["calculated_minutes"] == 90
    assert report["timing_checks"][0]["status"] == "passed"


def test_generation_prompt_blocks_unsupported_domain_frameworks_and_uncited_source_guidance(monkeypatch):
    from app.services import ai_gateway

    captured = {}

    def fake_generate(model, model_input, schema):
        captured["model_input"] = model_input
        return SimpleNamespace(
            id="fake-response",
            output_text=json.dumps(
                {
                    "title": "Draft",
                    "output_type": "writing",
                    "content": "A grounded draft that is long enough for validation.",
                    "applied_knowledge": [
                        {"asset_id": "asset_1", "usage_note": "Used the supplied guidance."}
                    ],
                    "design_choices": [],
                }
            ),
        )

    monkeypatch.setattr(ai_gateway, "generate", fake_generate)

    prepared = {
        "brief": {
            "situation": "Create a useful draft",
            "goal": "Use supplied knowledge",
            "audience": None,
            "constraints": [],
            "output_type": "writing",
            "retrieval_query": "use supplied knowledge",
        },
        "knowledge_unit_count": 1,
        "knowledge_units": [
            {
                "canonical_asset": {
                    "id": "asset_1",
                    "asset_type": "principle",
                    "title": "Use source guidance",
                    "what_it_says": "Ground recommendations in supplied knowledge.",
                    "why_it_matters": None,
                    "evidence": "Ground recommendations in supplied knowledge.",
                    "source_id": "source_1",
                },
                "support_count": 1,
                "chunk_ids": ["chunk_1"],
                "source_ids": ["source_1"],
                "asset_ids": ["asset_1"],
                "evidence_trail": [],
            }
        ],
        "synthesis_context": {},
    }

    payload = WorkshopGenerateRequest(
        situation="Create a useful draft",
        goal="Use supplied knowledge",
        output_type="writing",
        save=False,
    )

    generate_workshop_output(payload, prepared=prepared)

    instructions = captured["model_input"]["instructions"]
    assert "Do not invent domain-specific facts, definitions, frameworks, templates" in instructions
    assert "include its asset_id in applied_knowledge" in instructions
    assert "your organization's required SOP fields" in instructions
    assert "audit every specific multi-part list, number, threshold, timing" in instructions
    assert "Generator-created adaptations must also be visibly framed" in instructions
    assert "Do not coin a source-sounding name" in instructions


def _workshop_output(domain_line):
    return {
        "title": "SOP workshop",
        "output_type": "workshop_plan",
        "content": f"""## Learning Goals
Draft an SOP.
## Agenda
| Elapsed Minute Range | Activity |
| --- | --- |
| 0–15 min | Introduction |
| 15–30 min | Core concept |
| 30–45 min | Guided practice |
| 45–50 min | Break |
| 50–70 min | Independent practice |
| 70–90 min | Review and Q&A |
## Activities
{domain_line}
""",
        "applied_knowledge": [
            {"asset_id": "asset_1", "usage_note": "Used the supplied workshop guidance."}
        ],
        "design_choices": [],
    }


def _knowledge(what_it_says):
    return [
        {
            "canonical_asset": {
                "id": "asset_1",
                "asset_type": "principle",
                "title": "Workshop guidance",
                "what_it_says": what_it_says,
                "evidence": what_it_says,
                "source_id": "source_1",
            },
            "evidence_trail": [],
        }
    ]


def test_quality_review_flags_unsupported_specific_domain_component_list():
    output = _workshop_output(
        "Teach the essential SOP elements (Title, Scope, Steps, Troubleshooting)."
    )
    report = quality_report(
        output,
        {
            "situation": "Teach beginners to draft an SOP.",
            "goal": "Participants leave with a draft SOP.",
            "constraints": ["90 minutes total"],
        },
        _knowledge("Keep workshop teaching practical and concise."),
    )

    flags = [
        issue for issue in report["issues"]
        if issue["code"] == "unsupported_specific_list_needs_review"
    ]
    assert report["timing_checks"][0]["status"] == "passed"
    assert report["validation_status"] == "needs_review"
    assert len(flags) == 1
    assert "Troubleshooting" in flags[0]["unsupported_items"]


def test_supported_specific_domain_component_list_does_not_trigger_grounding_flag():
    output = _workshop_output(
        "Teach the essential SOP elements (Title, Scope, Steps, Troubleshooting)."
    )
    report = quality_report(
        output,
        {
            "situation": "Teach beginners to draft an SOP.",
            "goal": "Participants leave with a draft SOP.",
            "constraints": ["90 minutes total"],
        },
        _knowledge(
            "A usable SOP in this source has four required components: Title, Scope, Steps, Troubleshooting."
        ),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_specific_list_needs_review" not in codes
    assert report["validation_status"] == "checks_passed"


def _decision_output(content, design_choices=None):
    return {
        "title": "Decision brief",
        "output_type": "decision_brief",
        "content": content,
        "applied_knowledge": [
            {"asset_id": "asset_1", "usage_note": "Used the supplied guidance."}
        ],
        "design_choices": design_choices or [],
    }


def test_quality_review_flags_unframed_unsupported_derived_timing():
    output = _decision_output(
        "## Recommendation\nDedicate 15 minutes to Q&A as the schedule buffer.",
        ["Defined 15 minutes as a suggested buffer for this 90-minute workshop."],
    )
    report = quality_report(
        output,
        {
            "situation": "Design a 90-minute workshop.",
            "goal": "Balance teaching and discussion.",
            "constraints": [],
        },
        _knowledge("Use Q&A as a flexible schedule spring that can expand or contract."),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_derived_number_needs_review" in codes
    assert report["validation_status"] == "needs_review"


def test_quality_review_allows_tracked_and_visibly_framed_derived_timing():
    output = _decision_output(
        "## Recommendation\nOne possible allocation is 15 minutes for Q&A; adjust it to the session.",
        ["Suggested 15 minutes as one possible Q&A allocation for this 90-minute workshop."],
    )
    report = quality_report(
        output,
        {
            "situation": "Design a 90-minute workshop.",
            "goal": "Balance teaching and discussion.",
            "constraints": [],
        },
        _knowledge("Use Q&A as a flexible schedule spring that can expand or contract."),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_derived_number_needs_review" not in codes


def test_quality_review_flags_source_sounding_generated_method_name():
    output = _decision_output(
        "## Options\nUse The Iterative Pass Approach to build the workshop in several passes.",
        ["Named the multi-pass adaptation 'The Iterative Pass Approach' for this draft."],
    )
    report = quality_report(
        output,
        {
            "situation": "Design a workshop.",
            "goal": "Create a practical approach.",
            "constraints": [],
        },
        _knowledge("Work across the whole workshop in a series of passes, going deeper on each pass."),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_named_framework_needs_review" in codes
    assert report["validation_status"] == "needs_review"


def test_quality_review_allows_explicitly_generator_created_method_label():
    output = _decision_output(
        "## Options\nFor this draft, call this The Iterative Pass Approach: build the workshop in several passes.",
        ["For this draft, labeled the source-backed multi-pass idea 'The Iterative Pass Approach'."],
    )
    report = quality_report(
        output,
        {
            "situation": "Design a workshop.",
            "goal": "Create a practical approach.",
            "constraints": [],
        },
        _knowledge("Work across the whole workshop in a series of passes, going deeper on each pass."),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_named_framework_needs_review" not in codes


def test_quality_review_flags_unsupported_short_label_taxonomy():
    output = _decision_output(
        "## Next steps\nAssign 'K', 'S', or 'W' to every outline item before timing the workshop.",
        ["Assumed 'K', 'S', and 'W' labels as organizing tags."],
    )
    report = quality_report(
        output,
        {
            "situation": "Design a workshop.",
            "goal": "Create a practical approach.",
            "constraints": [],
        },
        _knowledge("Start from learning outcomes and refine the workshop in multiple passes."),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_taxonomy_needs_review" in codes
    assert report["validation_status"] == "needs_review"


def test_quality_review_allows_explicitly_generated_short_label_taxonomy():
    output = _decision_output(
        "## Next steps\nFor this draft, use 'K', 'S', and 'W' only as temporary organizing labels.",
        ["For this draft, assumed 'K', 'S', and 'W' as temporary organizing labels."],
    )
    report = quality_report(
        output,
        {
            "situation": "Design a workshop.",
            "goal": "Create a practical approach.",
            "constraints": [],
        },
        _knowledge("Start from learning outcomes and refine the workshop in multiple passes."),
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert "unsupported_taxonomy_needs_review" not in codes
