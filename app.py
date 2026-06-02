import json
from pathlib import Path

import streamlit as st

DATA_FOLDER = Path("data")

SOURCES_FILE = DATA_FOLDER / "sources.json"
CONCEPTS_FILE = DATA_FOLDER / "concepts.json"
PROBLEMS_FILE = DATA_FOLDER / "problems.json"
INSIGHTS_FILE = DATA_FOLDER / "insights.json"


def load_json(file_path):
    text = file_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    return json.loads(text)


def get_source_insights(source_id, insights):
    return [
        insight for insight in insights
        if insight.get("source_id") == source_id
    ]


def get_items_by_ids(items, ids):
    return [
        item for item in items
        if item.get("id") in ids
    ]


def clean_words(text):
    return [
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in text.split()
        if len(word.strip(".,!?;:()[]{}\"'")) > 3
    ]


def find_matching_insights(search_text, insights):
    query_words = clean_words(search_text.lower())

    matching_insights = []

    for insight in insights:
        insight_search_text = " ".join(
            [
                insight.get("title", ""),
                insight.get("what_it_says", ""),
                insight.get("why_it_matters", ""),
                " ".join(insight.get("keywords", [])),
                insight.get("knowledge_type", "")
            ]
        ).lower()

        match_count = sum(
            1 for word in query_words
            if word in insight_search_text
        )

        if match_count > 0:
            matching_insights.append(
                {
                    "insight": insight,
                    "match_count": match_count
                }
            )

    return sorted(
        matching_insights,
        key=lambda item: (
            item["match_count"],
            item["insight"].get("importance_score", 0),
            item["insight"].get("confidence_score", 0)
        ),
        reverse=True
    )


def collect_related_items(top_matches, concepts, problems):
    concept_ids = sorted(
        set(
            concept_id
            for item in top_matches
            for concept_id in item["insight"].get("concept_ids", [])
        )
    )

    problem_ids = sorted(
        set(
            problem_id
            for item in top_matches
            for problem_id in item["insight"].get("problem_ids", [])
        )
    )

    related_concepts = get_items_by_ids(concepts, concept_ids)
    related_problems = get_items_by_ids(problems, problem_ids)

    return related_concepts, related_problems


def unique_list(items):
    clean_items = []

    for item in items:
        if item and item not in clean_items:
            clean_items.append(item)

    return clean_items


def infer_audience_problem(situation, goal, audience, constraints, problem_names):
    combined_text = " ".join(
        [
            situation,
            goal,
            audience,
            constraints
        ]
    ).lower()

    if "ovara" in combined_text or "caribbean" in combined_text or "market" in combined_text:
        return (
            "People interested in Caribbean markets often face scattered, technical, "
            "and hard-to-use information, making it difficult to understand what matters "
            "and make clearer decisions."
        )

    if "linkedin" in combined_text or "post" in combined_text or "content" in combined_text:
        return (
            "The audience may scroll past the message unless the core idea is clear, "
            "concrete, and immediately relevant."
        )

    if "website" in combined_text or "landing page" in combined_text:
        return (
            "Visitors may not quickly understand what the product does, who it is for, "
            "or why it matters."
        )

    if "friend" in combined_text or "message" in combined_text or "ask" in combined_text:
        return (
            "The reader may not understand the seriousness of the situation or the specific "
            "kind of help being requested."
        )

    if problem_names:
        return problem_names[0]

    return "The audience may not immediately understand why this matters."


def build_draft_starter(situation, goal, audience, constraints):
    combined_text = " ".join(
        [
            situation,
            goal,
            audience,
            constraints
        ]
    ).lower()

    if "ovara" in combined_text:
        return (
            "Caribbean market information is often scattered, technical, and hard to turn into decisions. "
            "Ovara helps make that information clearer, more organized, and easier to act on."
        )

    if "linkedin" in combined_text or "post" in combined_text:
        return (
            "The clearest messages do not try to say everything at once. "
            "They lead with the one idea the audience needs to understand first."
        )

    if "website" in combined_text or "landing page" in combined_text:
        return (
            "A visitor should not have to work hard to understand what this is, who it helps, "
            "and why it matters."
        )

    if "friend" in combined_text or "ask" in combined_text:
        return (
            "I need to be honest about where I am right now, and I am asking because I trust you."
        )

    return (
        "Most people do not need more information. "
        "They need a clearer way to understand what the information means and what they can do with it."
    )


def build_writing_brief(situation, goal, audience, constraints, related_concepts, related_problems, matched_items):
    concept_names = [
        concept.get("name", "")
        for concept in related_concepts
        if concept.get("name")
    ]

    problem_names = [
        problem.get("name", "")
        for problem in related_problems
        if problem.get("name")
    ]

    decision_rules = []

    for item in matched_items:
        insight = item["insight"]

        for rule in insight.get("decision_rules", []):
            decision_rules.append(rule)

    examples = []

    for item in matched_items:
        insight = item["insight"]

        for example in insight.get("examples_from_source", []):
            examples.append(example)

        for old_example in insight.get("examples", []):
            examples.append(
                {
                    "example_name": old_example,
                    "transferable_lesson": ""
                }
            )

    warnings = []

    for item in matched_items:
        insight = item["insight"]

        for warning in insight.get("warnings", []):
            warnings.append(warning)

    core_message = goal.strip()

    if not core_message:
        core_message = situation.strip()

    audience_problem = infer_audience_problem(
        situation=situation,
        goal=goal,
        audience=audience,
        constraints=constraints,
        problem_names=problem_names
    )

    writing_rules = unique_list(
        [
            rule.get("rule", "")
            for rule in decision_rules
            if rule.get("rule", "")
        ]
    )[:6]

    example_lessons = unique_list(
        [
            example.get("transferable_lesson", "")
            for example in examples
            if example.get("transferable_lesson", "")
        ]
    )[:5]

    example_names = unique_list(
        [
            example.get("example_name", "")
            for example in examples
            if example.get("example_name", "")
        ]
    )[:5]

    warning_notes = unique_list(
        [
            warning.get("warning", "")
            for warning in warnings
            if warning.get("warning", "")
        ]
    )[:5]

    draft_starter = build_draft_starter(
        situation=situation,
        goal=goal,
        audience=audience,
        constraints=constraints
    )

    return {
        "core_message": core_message,
        "audience_problem": audience_problem,
        "concepts_to_use": concept_names[:8],
        "writing_rules": writing_rules,
        "example_lessons": example_lessons,
        "example_names": example_names,
        "warnings": warning_notes,
        "draft_starter": draft_starter,
        "revision_checklist": [
            "Is the core message clear in the first sentence?",
            "Is the audience problem specific rather than generic?",
            "Is the language concrete rather than abstract?",
            "Does the audience understand why this matters?",
            "Is there one main point instead of too many competing points?",
            "Is there an example, analogy, or familiar reference that makes the idea easier to understand?",
            "Did you remove jargon that makes the message harder to apply?",
            "Does the writing tell the reader what to do, think, or understand next?"
        ]
    }


sources = load_json(SOURCES_FILE)
concepts = load_json(CONCEPTS_FILE)
problems = load_json(PROBLEMS_FILE)
insights = load_json(INSIGHTS_FILE)

st.set_page_config(
    page_title="Knowledge Engine",
    layout="wide"
)

st.title("Knowledge Engine")
st.write("Turn books into concepts, problems, insights, examples, patterns, and decision rules.")

page = st.sidebar.radio(
    "Choose a view",
    [
        "Source Overview",
        "Explore Concept",
        "Search by Problem",
        "Knowledge Workshop"
    ]
)


if page == "Source Overview":
    st.header("Source Overview")

    source_titles = [source["title"] for source in sources]
    selected_title = st.selectbox("Select a source", source_titles)

    source = next(
        source for source in sources
        if source["title"] == selected_title
    )

    source_insights = get_source_insights(source["id"], insights)

    st.subheader(source["title"])
    st.write(f"Author: {source.get('author')}")
    st.write(f"Type: {source.get('source_type')}")
    st.write(f"Insights extracted: {len(source_insights)}")

    concept_ids = sorted(
        set(
            concept_id
            for insight in source_insights
            for concept_id in insight.get("concept_ids", [])
        )
    )

    problem_ids = sorted(
        set(
            problem_id
            for insight in source_insights
            for problem_id in insight.get("problem_ids", [])
        )
    )

    source_concepts = get_items_by_ids(concepts, concept_ids)
    source_problems = get_items_by_ids(problems, problem_ids)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Concepts")
        for concept in source_concepts:
            st.write(f"**{concept.get('name')}**")
            st.write(concept.get("description"))

    with col2:
        st.subheader("Problems")
        for problem in source_problems:
            st.write(f"**{problem.get('name')}**")
            st.write(problem.get("description"))

    st.subheader("Insights")

    for insight in source_insights:
        with st.expander(insight.get("title", "Untitled insight")):
            st.write("**What it says**")
            st.write(insight.get("what_it_says", ""))

            st.write("**Why it matters**")
            st.write(insight.get("why_it_matters", ""))

            st.write("**Evidence**")
            st.write(insight.get("evidence", ""))


if page == "Explore Concept":
    st.header("Explore Concept")

    concept_names = [concept["name"] for concept in concepts]
    selected_concept_name = st.selectbox("Select a concept", concept_names)

    concept = next(
        concept for concept in concepts
        if concept["name"] == selected_concept_name
    )

    concept_insights = [
        insight for insight in insights
        if concept["id"] in insight.get("concept_ids", [])
    ]

    st.subheader(concept["name"])
    st.write(concept.get("description"))

    st.write("### Related Insights")

    for insight in concept_insights:
        with st.expander(insight.get("title", "Untitled insight")):
            st.write(insight.get("what_it_says", ""))

            st.write("**Decision Rules**")
            for rule in insight.get("decision_rules", []):
                st.write(f"- {rule.get('rule')}")

            st.write("**Patterns**")
            for pattern in insight.get("patterns", []):
                st.write(f"- {pattern.get('pattern_name')}: {pattern.get('description')}")

            st.write("**Examples**")
            for example in insight.get("examples_from_source", []):
                st.write(f"- {example.get('example_name')}: {example.get('transferable_lesson')}")


if page == "Search by Problem":
    st.header("Search by Problem")

    query = st.text_input("What problem are you trying to solve?")

    if query:
        matching_problems = []

        for problem in problems:
            text = f"{problem.get('name', '')} {problem.get('description', '')}".lower()

            if any(word in text for word in query.lower().split()):
                matching_problems.append(problem)

        if not matching_problems:
            st.warning("No matching problems found yet.")
        else:
            for problem in matching_problems:
                st.subheader(problem["name"])
                st.write(problem["description"])

                related_insights = [
                    insight for insight in insights
                    if problem["id"] in insight.get("problem_ids", [])
                ]

                for insight in related_insights:
                    with st.expander(insight.get("title", "Untitled insight")):
                        st.write(insight.get("what_it_says", ""))

                        st.write("**Application Patterns**")
                        for pattern in insight.get("application_patterns", []):
                            st.write(f"- {pattern.get('pattern_name')}")
                            for step in pattern.get("steps", []):
                                st.write(f"  - {step}")


if page == "Knowledge Workshop":
    st.header("Knowledge Workshop")

    st.write(
        "Describe a real situation, choose what you want to do with the knowledge, "
        "and the app will turn relevant concepts, insights, rules, examples, and warnings into a usable workspace."
    )

    mode = st.selectbox(
        "What do you want to do with this knowledge?",
        [
            "Create or edit writing",
            "Generate copywriting brief",
            "Make a decision",
            "Create study guide",
            "Build playbook",
            "Prepare presentation"
        ]
    )

    situation = st.text_area(
        "What situation are you trying to work through?",
        placeholder="Example: I need to explain Ovara clearly on LinkedIn."
    )

    goal = st.text_input(
        "What outcome do you want?",
        placeholder="Example: Help people quickly understand what Ovara does and why it matters."
    )

    audience = st.text_input(
        "Who is the audience?",
        placeholder="Example: potential users, investors, founders, LinkedIn connections"
    )

    constraints = st.text_area(
        "Any constraints?",
        placeholder="Example: Keep it simple, human, and not too technical."
    )

    if st.button("Build workshop"):
        if not situation.strip():
            st.warning("Add a situation first.")
        else:
            search_text = " ".join(
                [
                    situation,
                    goal,
                    audience,
                    constraints,
                    mode
                ]
            ).lower()

            matching_insights = find_matching_insights(search_text, insights)

            if not matching_insights:
                st.warning(
                    "No strong matches found yet. Try words like communication, "
                    "message, audience, attention, simple, decision, or story."
                )
            else:
                top_matches = matching_insights[:8]
                related_concepts, related_problems = collect_related_items(
                    top_matches,
                    concepts,
                    problems
                )

                if mode in ["Create or edit writing", "Generate copywriting brief"]:
                    brief = build_writing_brief(
                        situation=situation,
                        goal=goal,
                        audience=audience,
                        constraints=constraints,
                        related_concepts=related_concepts,
                        related_problems=related_problems,
                        matched_items=top_matches
                    )

                    st.subheader("Writing Workshop Brief")

                    st.write("**Core Message**")
                    st.write(brief["core_message"])

                    st.write("**Audience Problem**")
                    st.write(brief["audience_problem"])

                    st.write("**Concepts to Use**")
                    for concept_name in brief["concepts_to_use"]:
                        st.write(f"- {concept_name}")

                    st.write("**Writing Rules**")
                    for rule in brief["writing_rules"]:
                        st.write(f"- {rule}")

                    st.write("**Examples to Borrow From**")
                    if brief["example_lessons"]:
                        for lesson in brief["example_lessons"]:
                            st.write(f"- {lesson}")
                    else:
                        for example_name in brief["example_names"]:
                            st.write(f"- {example_name}")

                    st.write("**Warnings to Avoid**")
                    for warning in brief["warnings"]:
                        st.write(f"- {warning}")

                    st.write("**Draft Starter**")
                    st.info(brief["draft_starter"])

                    st.write("**Revision Checklist**")
                    for checklist_item in brief["revision_checklist"]:
                        st.checkbox(checklist_item)

                else:
                    st.info(
                        "This workshop mode is not built yet. "
                        "For now, use Create or edit writing or Generate copywriting brief."
                    )

                st.divider()

                st.subheader("Relevant Concepts")

                if related_concepts:
                    for concept in related_concepts:
                        st.write(f"**{concept.get('name')}**")
                        st.write(concept.get("description", ""))
                else:
                    st.write("No related concepts found.")

                st.subheader("Relevant Problems")

                if related_problems:
                    for problem in related_problems:
                        st.write(f"**{problem.get('name')}**")
                        st.write(problem.get("description", ""))
                else:
                    st.write("No related problems found.")

                st.subheader("Recommended Decision Rules")

                found_rules = False

                for item in top_matches:
                    insight = item["insight"]

                    for rule in insight.get("decision_rules", []):
                        found_rules = True

                        st.write(f"**{rule.get('rule')}**")
                        st.write(f"Use when: {rule.get('condition', '')}")
                        st.write(f"Action: {rule.get('action', '')}")
                        st.caption(f"From: {insight.get('title', '')}")

                if not found_rules:
                    st.write("No decision rules found for this situation yet.")

                st.subheader("Useful Patterns")

                found_patterns = False

                for item in top_matches:
                    insight = item["insight"]

                    for pattern in insight.get("patterns", []):
                        found_patterns = True

                        with st.expander(pattern.get("pattern_name", "Pattern")):
                            st.write(pattern.get("description", ""))

                            steps = pattern.get("steps", [])

                            if steps:
                                st.write("Steps:")
                                for step in steps:
                                    st.write(f"- {step}")

                            st.caption(f"From: {insight.get('title', '')}")

                if not found_patterns:
                    st.write("No patterns found for this situation yet.")

                st.subheader("Examples to Learn From")

                found_examples = False

                for item in top_matches:
                    insight = item["insight"]

                    for example in insight.get("examples_from_source", []):
                        found_examples = True

                        with st.expander(example.get("example_name", "Example")):
                            st.write(f"**What happened:** {example.get('what_happened', '')}")
                            st.write(f"**Why it matters:** {example.get('why_it_matters', '')}")
                            st.write(f"**Transferable lesson:** {example.get('transferable_lesson', '')}")
                            st.caption(f"From: {insight.get('title', '')}")

                    for example in insight.get("examples", []):
                        found_examples = True
                        st.write(f"- {example}")
                        st.caption(f"From: {insight.get('title', '')}")

                if not found_examples:
                    st.write("No examples found for this situation yet.")

                st.subheader("Warnings")

                found_warnings = False

                for item in top_matches:
                    insight = item["insight"]

                    for warning in insight.get("warnings", []):
                        found_warnings = True

                        with st.expander(warning.get("warning", "Warning")):
                            st.write(f"**Consequence:** {warning.get('consequence', '')}")
                            st.write(f"**Prevention:** {warning.get('prevention', '')}")
                            st.caption(f"From: {insight.get('title', '')}")

                if not found_warnings:
                    st.write("No warnings found for this situation yet.")

                st.subheader("Relevant Insights")

                for item in top_matches:
                    insight = item["insight"]

                    with st.expander(insight.get("title", "Untitled insight")):
                        st.write("**What it says**")
                        st.write(insight.get("what_it_says", ""))

                        st.write("**Why it matters**")
                        st.write(insight.get("why_it_matters", ""))

                        st.write("**Evidence**")
                        st.write(insight.get("evidence", ""))
