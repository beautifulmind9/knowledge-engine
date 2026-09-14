from app.services.knowledge_extraction_prompt import build_knowledge_extraction_request


def test_prompt_scans_past_front_matter_before_empty_extraction():
    chunk = {
        "id": "chunk_front_matter_then_content",
        "source_id": "source_front_matter",
        "text": (
            "Contents\nPublication details\n"
            "Substantive section: Every workshop lives or dies by what the audience learns "
            "and how the audience feels."
        ),
    }

    request = build_knowledge_extraction_request(chunk)
    instructions = request["instructions"]

    assert "Scan the entire chunk before deciding it has no reusable knowledge" in instructions
    assert "Ignore the non-reusable front matter" in instructions
    assert "Do not return an empty assets list solely because the chunk begins with front matter" in instructions
    assert request["chunk_text"] == chunk["text"]
    assert request["source_id"] == chunk["source_id"]
    assert request["chunk_id"] == chunk["id"]


def test_prompt_uses_explicit_confidence_calibration_rubric():
    chunk = {
        "id": "chunk_confidence",
        "source_id": "source_confidence",
        "text": "Use practice breaks to help participants retain learning.",
    }

    instructions = build_knowledge_extraction_request(chunk)["instructions"]

    assert "Confidence measures how directly the source supports the asset" in instructions
    assert "A faithful paraphrase or near-verbatim restatement can and should be 5" in instructions
    assert "Only minimal synthesis is required" in instructions
    assert "meaningful interpretation, generalization, or inference is required" in instructions
    assert "Never default to 3" in instructions
    assert "Do not lower a plainly stated asset to 3" in instructions
    assert "Do not force any confidence score to appear" in instructions
