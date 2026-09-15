import json
from types import SimpleNamespace

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.output_modes import quality_report
from app.services.workshop_generation import generate_workshop_output


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
