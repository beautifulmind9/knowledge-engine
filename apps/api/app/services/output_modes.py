MODES = {
    "writing": {"label": "Writing / editing", "instructions": "Produce ready-to-use copy for the stated channel. Use a clear opening, audience-specific body and an appropriate closing or call to action. Do not wrap copy in an essay about writing.", "checks": []},
    "decision_brief": {"label": "Decision brief", "instructions": "Use headings: Decision, Options, Trade-offs, Recommendation, Uncertainties, Next steps. Distinguish facts from assumptions. Do not invent scores or certainty.", "checks": ["Options", "Recommendation", "Uncertainties"]},
    "study_guide": {"label": "Study guide", "instructions": "Use headings: Learning goals, Key ideas, Practice, Review questions. Include answers or checking guidance after the questions.", "checks": ["Key ideas", "Practice", "Review questions"]},
    "product_messaging": {"label": "Product messaging", "instructions": "Use headings: Audience, Value proposition, Supporting messages, Draft copy. Identify unsupported product promises as assumptions, never verified facts.", "checks": ["Audience", "Value proposition", "Draft copy"]},
    "playbook": {"label": "Playbook / process", "instructions": "Use headings: Purpose, Prerequisites, Steps, Checks, Exceptions. Give numbered, actionable steps and explicit completion checks.", "checks": ["Steps", "Checks", "Exceptions"]},
    "workshop_plan": {"label": "Workshop plan", "instructions": "Include learning goals, timed agenda, breaks, activities and completion checks. Reconcile the total time with the brief. Label derived timings as design choices.", "checks": ["Agenda", "Break", "Activities"]},
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
