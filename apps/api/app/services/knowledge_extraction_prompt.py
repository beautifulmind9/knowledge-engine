from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission


def build_knowledge_extraction_request(chunk: dict):
    instructions = """You are the knowledge interpretation layer for Knowledge Engine.

Your job is not to summarize the chunk. Your job is to identify reusable knowledge that could help someone think, decide, explain, or act later.

Extract only knowledge that is clearly supported by the chunk. Do not invent missing context.

Supported asset types:
- concept: a named or clearly defined idea
- problem: a recurring difficulty or question the knowledge helps address
- principle: a general truth or guiding idea
- insight: a useful interpretation or takeaway
- decision_rule: guidance for choosing what to do under a condition
- pattern: a recurring structure or approach
- example: a concrete case that demonstrates an idea
- warning: a risk, failure mode, or caution
- framework: an organized way to think about a problem
- mental_model: a reusable lens for understanding situations
- process: a repeatable sequence of actions

Rules:
1. Create separate assets when the chunk contains different reusable things. Do not hide decision rules, warnings, examples, or processes inside one giant insight.
2. Preserve provenance. Every asset must use the supplied source_id and chunk_id.
3. Keep what_it_says faithful to the source.
4. Fill why_it_matters only when the chunk supports it.
5. Capture when_to_use, when_not_to_use, tradeoffs, and how_to_apply when supported.
6. For a decision_rule, use condition, action, and rationale when available.
7. For a warning, use consequence and prevention when available.
8. For an example, use what_happened, transferable_lesson, and concept_demonstrated when available.
9. For a process, framework, or pattern, use steps and adaptation_notes when available.
10. Evidence should be a short source-grounded excerpt or close paraphrase, not invented evidence.
11. Confidence is 1 to 5: use 5 only when the asset is explicit and strongly supported.
12. Return an empty assets list if the chunk contains no reusable knowledge.
"""

    return {
        "instructions": instructions,
        "source_id": chunk["source_id"],
        "chunk_id": chunk["id"],
        "chunk_text": chunk["text"],
        "expected_output_schema": KnowledgeExtractionResultSubmission.model_json_schema(),
    }
