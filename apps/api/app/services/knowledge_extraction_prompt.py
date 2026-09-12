from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission


def build_knowledge_extraction_request(chunk: dict):
    instructions = """You are the knowledge interpretation layer for Knowledge Engine.

Your job is not to summarize the chunk. Your job is to identify reusable knowledge that could help someone think, decide, explain, or act later.

Extract only knowledge that is clearly supported by the chunk. Do not invent missing context.

Supported asset types:
- concept: a named or clearly defined idea
- problem: a recurring difficulty or question the knowledge helps address
- principle: a general truth or guiding idea
- insight: a useful interpretation or takeaway that does not fit a more specific type
- decision_rule: guidance for choosing what to do under a condition
- pattern: a recurring structure or approach
- example: a concrete case that demonstrates an idea
- warning: a risk, failure mode, or caution
- framework: an organized way to think about a problem
- mental_model: a reusable lens for understanding situations
- process: a repeatable sequence of actions

Rules:
1. Create separate assets when the chunk contains genuinely different reusable things.
2. Do not create duplicate assets that merely restate the same knowledge under different types.
3. Prefer the most specific asset type. If something is clearly a decision rule, warning, example, process, framework, pattern, or concept, use that type instead of also creating a generic insight for the same idea.
4. Use insight only when the useful takeaway does not fit a more specific supported type.
5. Preserve provenance. Every asset must use the supplied source_id and chunk_id.
6. Keep what_it_says faithful to the source.
7. Fill why_it_matters only when the chunk supports it.
8. Capture when_to_use, when_not_to_use, tradeoffs, and how_to_apply when supported.
9. For a decision_rule, always populate action with the concrete behavior or choice the rule recommends. Use condition and rationale when supported. Do not create a decision_rule if no action can be stated from the source.
10. For a warning, use consequence and prevention when available.
11. For an example, use what_happened, transferable_lesson, and concept_demonstrated when available.
12. For a process, always provide steps. For a framework or pattern, provide steps and adaptation_notes when supported.
13. Evidence should be a short source-grounded excerpt or close paraphrase, not invented evidence.
14. Confidence is 1 to 5. Use 5 when the asset is explicitly stated in the chunk and strongly supported; use lower scores when interpretation is required.
15. Add a small set of grounded keywords using terms that appear in, or are direct labels for, the source content.
16. Do not force every asset type to appear. Extract only what the chunk actually supports.
17. Return an empty assets list if the chunk contains no reusable knowledge.
"""

    return {
        "instructions": instructions,
        "source_id": chunk["source_id"],
        "chunk_id": chunk["id"],
        "chunk_text": chunk["text"],
        "expected_output_schema": KnowledgeExtractionResultSubmission.model_json_schema(),
    }
