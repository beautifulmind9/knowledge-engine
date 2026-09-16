MODES = {
    "writing": {"label": "Writing / editing", "instructions": "Produce ready-to-use copy for the stated channel. Use a clear opening, audience-specific body and an appropriate closing or call to action. Do not wrap copy in an essay about writing.", "checks": []},
    "knowledge_answer": {"label": "Knowledge answer / synthesis", "instructions": "Answer the user's question directly from the retrieved knowledge. Distinguish what the source teaches from your own synthesis. Surface relevant concepts, problems, examples, warnings, patterns, frameworks, and decision rules when they materially answer the question. Preserve uncertainty, source scope, and tensions instead of smoothing them over.", "checks": []},
    "research_synthesis": {"label": "Research / synthesis brief", "instructions": "Use headings: Question, Synthesis, Supporting ideas, Agreements and tensions, Application, Gaps. Combine relevant knowledge across sources without treating overlap as proof of consensus. Keep disagreements and scope differences visible.", "checks": ["Synthesis", "Supporting ideas", "Gaps"]},
    "decision_brief": {"label": "Decision brief", "instructions": "Use headings: Decision, Options, Trade-offs, Recommendation, Uncertainties, Next steps. Distinguish facts from assumptions. Do not invent scores or certainty.", "checks": ["Options", "Recommendation", "Uncertainties"]},
    "study_guide": {"label": "Study guide", "instructions": "Use headings: Learning goals, Key ideas, Practice, Review questions. Include answers or checking guidance after the questions.", "checks": ["Key ideas", "Practice", "Review questions"]},
    "social_content": {"label": "Content / social media", "instructions": "Create publishable content in the requested output format. Lead with a strong idea, make the source-grounded insight understandable without overclaiming, and adapt structure and length to the requested channel. For carousel formats, organize the content slide by slide. For short-form video, write a spoken script rather than an essay. For captions or posts, return the copy itself rather than commentary about the copy.", "checks": [], "formats": ["LinkedIn post", "Instagram caption", "Carousel", "Short-form video script", "Thread", "Long-form article", "Content ideas"]},
    "product_messaging": {"label": "Product messaging", "instructions": "Use headings: Audience, Value proposition, Supporting messages, Draft copy. Identify unsupported product promises as assumptions, never verified facts.", "checks": ["Audience", "Value proposition", "Draft copy"]},
    "playbook": {"label": "Playbook / process", "instructions": "Use headings: Purpose, Prerequisites, Steps, Checks, Exceptions. Give numbered, actionable steps and explicit completion checks.", "checks": ["Steps", "Checks", "Exceptions"]},
    "action_plan": {"label": "Action plan", "instructions": "Use headings: Objective, Priorities, Actions, Risks, Next steps. Turn the retrieved knowledge into a practical sequence of actions. Keep source-backed guidance distinct from generator-created ordering, timing, prioritization, or assumptions.", "checks": ["Actions", "Risks", "Next steps"]},
    "presentation": {"label": "Presentation / talking points", "instructions": "Create a clear presentation structure with a narrative arc, slide or section outline, and speaker talking points. Keep slide content concise and put fuller explanations in the talking points. Do not invent supporting facts that are absent from the brief or supplied knowledge.", "checks": ["Talking points"], "formats": ["Slide outline", "Speaker talking points", "Presentation outline + talking points"]},
    "workshop_plan": {"label": "Workshop / facilitation plan", "instructions": "Include learning goals, timed agenda, breaks, activities and completion checks. Reconcile the total time with the brief. Label derived timings as design choices.", "checks": ["Agenda", "Break", "Activities"]},
}


def quality_report(output, brief=None, knowledge_snapshot=None):
    brief = brief or {}
    knowledge_snapshot = knowledge_snapshot or []
    mode = MODES.get(output["output_type"], {"checks": []})
    structural = [{"criterion": word, "passed": word.lower() in output["content"].lower()} for word in mode["checks"]]
    report = {"report_version": 5, "validation_status": "not_evaluated", "issues": [],
            "structure_checks": structural, "has_provenance": bool(output["applied_knowledge"]),
            "human_review_required": True, "human_review_criteria": ["Ready-to-use artifact", "Audience and channel fit", "Source faithfulness", "Design choices separated"],
            "note": "Headings and citation IDs do not establish that a plan is valid. Even passed automated checks require human review of meaning and source faithfulness."}
    if output["output_type"] == "workshop_plan":
        from app.services.workshop_validation import validate_workshop
        report.update(validate_workshop(output, brief, knowledge_snapshot))

    from app.services.grounding_validation import grounding_review_issues
    grounding_issues = grounding_review_issues(output, brief, knowledge_snapshot)
    if grounding_issues:
        report.setdefault("issues", []).extend(grounding_issues)
        if report.get("validation_status") not in {"failed"}:
            report["validation_status"] = "needs_review"
    return report
