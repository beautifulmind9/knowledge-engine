from pathlib import Path
from datetime import date
import json

chunk_root = Path("outputs/chunks")
analysis_folder = Path("outputs/analysis")

sources_file = Path("data/sources.json")
concepts_file = Path("data/concepts.json")
problems_file = Path("data/problems.json")

analysis_folder.mkdir(parents=True, exist_ok=True)

chunk_files = sorted(chunk_root.glob("*/*.txt"))

print(f"Found {len(chunk_files)} chunk file(s)")

sources = json.loads(sources_file.read_text(encoding="utf-8"))
concepts_text = concepts_file.read_text(encoding="utf-8")
problems_text = problems_file.read_text(encoding="utf-8")

source = sources[0]

source_id = source["id"]
source_title = source["title"]
author = source["author"]

classification = source.get("classification", {})
extraction_lenses = source.get("extraction_lenses", [])
knowledge_priority = source.get("knowledge_priority", [])
monetization_use_cases = source.get("monetization_use_cases", [])

sources_text = json.dumps(sources, indent=2)

chunks_to_analyze = chunk_files[15:20]

schema = {
    "concepts": [
        {
            "id": "",
            "name": "",
            "description": "",
            "keywords": []
        }
    ],
    "problems": [
        {
            "id": "",
            "name": "",
            "description": ""
        }
    ],
    "insights": [
        {
            "id": "",
            "source_id": source_id,
            "source_title": source_title,
            "author": author,
            "chunk_file": "",
            "chapter_or_section": "",
            "concept_ids": [],
            "problem_ids": [],
            "title": "",
            "knowledge_type": "",
            "what_it_says": "",
            "why_it_matters": "",
            "examples_from_source": [
                {
                    "example_name": "",
                    "what_happened": "",
                    "why_it_matters": "",
                    "concept_demonstrated": "",
                    "transferable_lesson": ""
                }
            ],
            "decision_rules": [
                {
                    "rule": "",
                    "condition": "",
                    "action": "",
                    "rationale": ""
                }
            ],
            "patterns": [
                {
                    "pattern_name": "",
                    "description": "",
                    "steps": []
                }
            ],
            "warnings": [
                {
                    "warning": "",
                    "consequence": "",
                    "prevention": ""
                }
            ],
            "application_patterns": [
                {
                    "pattern_name": "",
                    "when_to_use": "",
                    "steps": [],
                    "adaptation_notes": ""
                }
            ],
            "when_to_use": [],
            "when_not_to_use": [],
            "tradeoffs": [],
            "keywords": [],
            "confidence_score": 0,
            "importance_score": 0,
            "novelty_score": 0,
            "evidence": "",
            "extraction_date": str(date.today())
        }
    ],
    "relationships": [
        {
            "from": "",
            "relationship": "",
            "to": "",
            "evidence": ""
        }
    ]
}

schema_text = json.dumps(schema, indent=2)
classification_text = json.dumps(classification, indent=2)
extraction_lenses_text = json.dumps(extraction_lenses, indent=2)
knowledge_priority_text = json.dumps(knowledge_priority, indent=2)
monetization_use_cases_text = json.dumps(monetization_use_cases, indent=2)

for chunk_file in chunks_to_analyze:
    print(f"\nPreparing insight extraction prompt for: {chunk_file.name}")

    chunk_text = chunk_file.read_text(encoding="utf-8")

    prompt = f"""
You are a knowledge extraction assistant.

Extract reusable knowledge for a hybrid knowledge graph.

The graph contains:

1. Sources
2. Concepts
3. Problems
4. Insights
5. Relationships

Definitions:

- A source is where information comes from.
- A concept is a reusable idea that can appear across many sources.
- A problem is a reusable challenge, obstacle, question, or decision.
- An insight is what a source says about a concept and/or problem.
- A relationship connects sources, concepts, problems, and insights.

====================
SOURCE CLASSIFICATION
====================

{classification_text}

====================
EXTRACTION LENSES
====================

Use these lenses to decide what to pay attention to:

{extraction_lenses_text}

====================
KNOWLEDGE PRIORITY
====================

Prioritize extracting these knowledge types when clearly present:

{knowledge_priority_text}

====================
MONETIZATION USE CASES
====================

This knowledge may later support these products or use cases:

{monetization_use_cases_text}

====================
EXISTING SOURCES
====================

{sources_text}

====================
EXISTING CONCEPTS
====================

{concepts_text}

====================
EXISTING PROBLEMS
====================

{problems_text}

====================
SOURCE CHUNK
====================

Chunk file:
{chunk_file}

Extraction date:
{date.today()}

====================
TEXT TO ANALYZE
====================

{chunk_text}

====================
INSTRUCTIONS
====================

Extract reusable knowledge from this chunk.

If this chunk is mostly:

- front matter
- copyright information
- table of contents
- acknowledgements
- incomplete context

Return:

{{
  "concepts": [],
  "problems": [],
  "insights": [],
  "relationships": []
}}

Return ONLY valid JSON.

Do not include markdown.

Do not include explanations outside the JSON.

Do not invent unsupported ideas.

Use this exact JSON structure:

{schema_text}

Rules:

- Concepts should be reusable ideas.
- Problems should be reusable challenges.
- Insights should explain what the source says.
- Use existing concepts and problems when appropriate.
- Create new concepts and problems only when needed.
- Follow the extraction lenses.
- Prioritize the knowledge types listed in knowledge_priority.
- Think about how the knowledge could later support the monetization use cases, but do not force commercial relevance if the text does not support it.

Capture examples whenever they help explain an idea.

For examples capture:
- what happened
- why it matters
- concept demonstrated
- transferable lesson

Capture decision rules whenever the source provides guidance for making choices.

Capture patterns whenever the source provides a repeatable structure or method.

Capture warnings whenever the source identifies a common mistake, misconception, or risk.

Capture application patterns whenever the source provides reusable methods.

Capture analogies if the source uses one domain, story, or comparison to explain another.

If analogies appear, place them under examples_from_source or application_patterns for now.

Do not force examples, decision rules, patterns, warnings, analogies, or application patterns if they are not clearly present.

Also identify if the source contains:
- Example
- Counterexample
- Checklist
- Exercise
- Warning
- Template
- Decision Rule
- Analogy
- Story
- Framework
- Method
- Operating principle
- Communication pattern
- Strategic tradeoff

Evidence must come directly from the text.

Scores should be 1-5.

Relationship examples:

- {source_id} contains concept_001
- {source_id} discusses problem_001
- insight_001 supports concept_001
- insight_001 addresses problem_001
- concept_001 helps_solve problem_001
- concept_001 related_to concept_002
"""

    output_file = analysis_folder / f"{chunk_file.stem}_insight_prompt.txt"

    output_file.write_text(prompt, encoding="utf-8")

    print(f"Saved prompt to: {output_file}")

print("\nDone.")