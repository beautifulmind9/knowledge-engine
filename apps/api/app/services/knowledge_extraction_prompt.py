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
- framework: an organized way to think about a problem, made of named components
- mental_model: a reusable lens for understanding situations
- process: a repeatable sequence of actions

Rules:
1. Extract a small number of high-value assets. Do not turn every sentence into an asset.
2. Create separate assets when the chunk contains genuinely different reusable things.
3. Do not create duplicate or heavily overlapping assets that merely restate the same knowledge under different titles or types.
4. Prefer the most specific asset type. If something is clearly a decision rule, warning, example, process, framework, pattern, or concept, use that type instead of also creating a generic insight for the same idea.
5. A decision_rule must help a future user make a choice or decide what to do. It must contain a concrete source-supported action. A descriptive statement about what the book covers, who it is for, or the scope of the author's method is NOT a decision rule.
6. If the source explicitly calls something a decision rule, or the knowledge clearly has a condition plus a recommended choice or behavior, classify it as decision_rule rather than concept, principle, or insight.
7. A concept names or defines an idea. Do not use concept for an instruction, recommendation, choice rule, warning, or process.
8. Use insight only when the useful takeaway does not fit a more specific supported type.
9. Source logistics, table-of-contents material, author credentials, publication details, and scope disclaimers should normally be omitted unless they contain genuinely reusable knowledge.
10. Preserve provenance. Every asset must use the supplied source_id and chunk_id.
11. Keep what_it_says faithful to the source.
12. Fill why_it_matters only when the chunk supports it.
13. Every asset must include evidence: a short source-grounded excerpt or close paraphrase that directly supports the asset.
14. Every asset must include 1 to 8 grounded keywords using terms that appear in, or are direct labels for, the source content.
15. Capture when_to_use, when_not_to_use, tradeoffs, and how_to_apply when supported.
16. For a decision_rule, always populate action with the concrete behavior or choice the rule recommends. Use condition and rationale when supported. Do not create a decision_rule if no action can be stated from the source.
17. For a warning, use consequence and prevention when available.
18. For an example, use what_happened, transferable_lesson, and concept_demonstrated when available.
19. For a process, always provide ordered steps.
20. For a framework, always provide its named components. Only use steps as well if the source presents an ordered procedure for using the framework.
21. For a pattern, provide steps and adaptation_notes when supported.
22. Confidence is 1 to 5. Use 5 when the asset is explicitly stated and directly supported by the evidence; use 4 when it is strongly implied; use 3 when meaningful interpretation is required. Do not default to 3 when the source states the asset plainly.
23. Do not force every asset type to appear. Extract only what the chunk actually supports.
24. Return an empty assets list if the chunk contains no reusable knowledge.
"""

    return {
        "instructions": instructions,
        "source_id": chunk["source_id"],
        "chunk_id": chunk["id"],
        "chunk_text": chunk["text"],
        "expected_output_schema": KnowledgeExtractionResultSubmission.model_json_schema(),
    }
