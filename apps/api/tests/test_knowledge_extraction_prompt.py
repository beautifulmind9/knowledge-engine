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


def _candidate_request():
    # Reuse the existing synthetic workshop domain; no private acceptance data.
    return build_knowledge_extraction_request({
        'id': 'chunk_test', 'source_id': 'source_test',
        'text': 'Switch formats every 20 minutes and match the format to the lesson.',
    })


def test_coverage_priority_has_no_asset_count_target():
    import re
    instructions = _candidate_request()['instructions']
    assert 'Preserve all important, independently reusable, source-supported knowledge' in instructions
    assert 'before optimizing for concision' in instructions
    assert 'small number of high-value assets' not in instructions
    assert 'Do not turn every sentence or paragraph into an asset or target a particular number of assets' in instructions
    # Ignore numbered rule labels; reject an introduced numeric asset quota.
    assert not re.search(r'\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:to\s+\d+\s+)?assets\b', instructions, re.I)
    asset_array = _candidate_request()['expected_output_schema']['properties']['assets']
    assert 'maxItems' not in asset_array
    assert 'minItems' not in asset_array


def test_material_qualifications_and_reusable_limits_are_explicit():
    instructions = _candidate_request()['instructions']
    assert 'conditions, exceptions, limitations, decision authority, responsibility acceptance, and safety exceptions' in instructions
    assert 'when they materially change meaning or application' in instructions
    assert 'Keep these qualifications with the knowledge they constrain' in instructions
    assert 'Omit incidental source logistics' in instructions
    assert 'non-reusable disclaimers' in instructions
    assert 'Retain source-supported applicability boundaries and limitations' in instructions


def test_concision_preserves_atomicity_and_no_duplication():
    instructions = _candidate_request()['instructions']
    assert 'coherent grouping and avoidance of duplication, while preserving atomicity' in instructions
    assert 'Do not create duplicate or heavily overlapping assets' in instructions
    assert 'independently retrieved and applied' in instructions
    assert 'extract independently useful rules separately' in instructions


def test_no_invention_and_optional_guidance_remain_conditional():
    from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
    instructions = _candidate_request()['instructions']
    assert 'Extract only knowledge that is clearly supported by the chunk. Do not invent missing context.' in instructions
    assert 'do not fill optional fields merely for completeness or invent missing qualifications' in instructions
    assert 'when supported and appropriate' in instructions
    assert 'Evidence must directly support every core claim' in instructions
    # Contract test only: empty optional guidance remains valid, not a semantic pass.
    parsed = KnowledgeExtractionResultSubmission(assets=[{
        'asset_type':'principle', 'title':'Match the format',
        'what_it_says':'Match the format to the lesson.',
        'evidence':'match the format to the lesson', 'keywords':['format'],
        'source_id':'source_test','chunk_id':'chunk_test',
    }])
    assert parsed.assets[0].when_to_use == []
    assert parsed.assets[0].when_not_to_use == []
    assert parsed.assets[0].tradeoffs == []
    assert parsed.assets[0].how_to_apply == []
