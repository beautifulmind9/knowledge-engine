"""Conservative local review signals for source grounding.

These checks do not prove that prose is faithful. They only surface a narrow
class of specific-looking claims that are easy for a generator to invent while
still sounding plausible.
"""
import re


PARENTHETICAL = re.compile(r"\((?P<body>[^()\n]{3,240})\)")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _flatten_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _flatten_strings(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _flatten_strings(nested)


def _support_corpus(brief: dict, knowledge_snapshot: list[dict]) -> str:
    parts = []
    for key in ("situation", "goal", "audience", "constraints"):
        parts.extend(_flatten_strings(brief.get(key)))
    for group in knowledge_snapshot:
        # Include the supplied knowledge itself, not generation metadata.
        parts.extend(_flatten_strings(group.get("canonical_asset", {})))
        parts.extend(_flatten_strings(group.get("evidence_trail", [])))
    return _normalize(" ".join(parts))


def _specific_parenthetical_lists(content: str):
    """Yield short comma-separated lists that look like named components.

    This intentionally ignores ordinary prose and long sentences. It is a
    review heuristic, not a semantic claim detector.
    """
    for match in PARENTHETICAL.finditer(content or ""):
        body = match.group("body")
        if body.count(",") < 2:
            continue
        items = [item.strip(" \t'\".*`)[]") for item in body.split(",")]
        if not 3 <= len(items) <= 8:
            continue
        if any(not item or len(item.split()) > 6 or len(item) > 60 for item in items):
            continue
        if any(not re.search(r"[A-Za-z]", item) for item in items):
            continue
        yield items


def grounding_review_issues(output: dict, brief: dict, knowledge_snapshot: list[dict]):
    """Return conservative review issues for unsupported specific-looking lists."""
    corpus = _support_corpus(brief or {}, knowledge_snapshot or [])
    issues = []
    seen = set()

    for items in _specific_parenthetical_lists(output.get("content", "")):
        normalized = [_normalize(item) for item in items]
        unsupported = [
            item for item, normalized_item in zip(items, normalized)
            if normalized_item and normalized_item not in corpus
        ]
        # Require multiple unsupported components and at least half the list so
        # one generic word (for example "steps") cannot make a fabricated
        # framework look supported.
        if len(unsupported) < 2 or len(unsupported) * 2 < len(items):
            continue
        signature = tuple(normalized)
        if signature in seen:
            continue
        seen.add(signature)
        issues.append(
            {
                "code": "unsupported_specific_list_needs_review",
                "severity": "review",
                "message": (
                    "The output introduces a specific multi-part list that is not "
                    "sufficiently supported by the brief or retrieved knowledge: "
                    + "; ".join(items)
                    + ". Replace it with neutral wording or supply knowledge that "
                    "supports those components."
                ),
                "items": items,
                "unsupported_items": unsupported,
            }
        )

    return issues
