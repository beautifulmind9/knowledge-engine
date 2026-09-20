"""Conservative local review signals for source grounding.

These checks do not prove that prose is faithful. They surface a few
specific-looking claim classes that generators commonly invent while still
sounding plausible: component lists, derived numbers presented as source rules,
and source-sounding names/taxonomies that are not present in the supplied
knowledge.
"""
import re


PARENTHETICAL = re.compile(r"\((?P<body>[^()\n]{3,240})\)")
NUMBER_WITH_UNIT = re.compile(
    r"(?<![\w.])(?P<first>\d+(?:\.\d+)?)"
    r"(?:\s*[-–]\s*(?P<second>\d+(?:\.\d+)?))?"
    r"\s*(?P<unit>minutes?|mins?|hours?|hrs?|seconds?|secs?|days?|weeks?|%|percent)\b",
    re.IGNORECASE,
)
NAMED_METHOD = re.compile(
    r"\b(?P<name>(?:The\s+)?(?:[A-Z][A-Za-z0-9'’-]*\s+){1,5}"
    r"(?:Approach|Framework|Model|Method|System|Taxonomy|Matrix|Formula))\b"
)
QUOTED_SHORT_LABEL = re.compile(r"['\"](?P<label>[A-Za-z][A-Za-z0-9/-]{0,5})['\"]")
ADAPTATION_MARKERS = (
    "one possible",
    "one option",
    "for example",
    "for this draft",
    "in this draft",
    "for this output",
    "illustrative",
    "suggested",
    "suggestion",
    "proposed",
    "could",
    "might",
    "consider",
    "adapt",
    "assumption",
    "assume",
    "i'll call",
    "we'll call",
    "call this",
    "label this",
)


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


def _support_strings(brief: dict, knowledge_snapshot: list[dict]) -> list[str]:
    parts = []
    for key in ("situation", "goal", "audience", "constraints"):
        parts.extend(_flatten_strings(brief.get(key)))
    for group in knowledge_snapshot:
        # Include the supplied knowledge itself, not generation metadata.
        parts.extend(_flatten_strings(group.get("canonical_asset", {})))
        parts.extend(_flatten_strings(group.get("evidence_trail", [])))
    return parts


def _support_corpus(brief: dict, knowledge_snapshot: list[dict]) -> str:
    return _normalize(" ".join(_support_strings(brief, knowledge_snapshot)))


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


def _unit(value: str) -> str:
    normalized = value.lower()
    aliases = {
        "mins": "minute",
        "min": "minute",
        "minutes": "minute",
        "hrs": "hour",
        "hr": "hour",
        "hours": "hour",
        "secs": "second",
        "sec": "second",
        "seconds": "second",
        "days": "day",
        "weeks": "week",
        "percent": "%",
    }
    return aliases.get(normalized, normalized.rstrip("s"))


def _number_signature(match) -> tuple[str, str | None, str]:
    first = match.group("first")
    second = match.group("second")
    return first, second, _unit(match.group("unit"))


def _number_signatures(text: str) -> set[tuple[str, str | None, str]]:
    return {_number_signature(match) for match in NUMBER_WITH_UNIT.finditer(text or "")}


def _context(text: str, start: int, end: int, radius: int = 140) -> str:
    return (text or "")[max(0, start - radius): min(len(text or ""), end + radius)]


def _is_visibly_adapted(context: str) -> bool:
    lowered = (context or "").lower()
    return any(marker in lowered for marker in ADAPTATION_MARKERS)


def _choice_text(output: dict) -> str:
    return "\n".join(str(value) for value in output.get("design_choices", []) if value)


def _unsupported_number_issues(output: dict, brief: dict, knowledge_snapshot: list[dict]):
    support_signatures = _number_signatures("\n".join(_support_strings(brief, knowledge_snapshot)))
    choice_signatures = _number_signatures(_choice_text(output))
    issues = []
    seen = set()
    content = output.get("content", "") or ""

    for match in NUMBER_WITH_UNIT.finditer(content):
        signature = _number_signature(match)
        if signature in support_signatures or signature in seen:
            continue
        seen.add(signature)
        context = _context(content, match.start(), match.end())
        # A generator-created quantity is acceptable only when the prose itself
        # frames it as an adaptation/example AND the choice is tracked.
        if _is_visibly_adapted(context) and signature in choice_signatures:
            continue
        display = match.group(0)
        issues.append(
            {
                "code": "unsupported_derived_number_needs_review",
                "severity": "review",
                "message": (
                    f"The output uses {display!r} as guidance, but that quantity is not "
                    "supported by the brief or retrieved knowledge and is not both visibly "
                    "framed as an adaptation and tracked in design choices."
                ),
                "value": display,
            }
        )
    return issues


def _unsupported_named_method_issues(output: dict, brief: dict, knowledge_snapshot: list[dict]):
    corpus = _support_corpus(brief, knowledge_snapshot)
    choices = _normalize(_choice_text(output))
    content = output.get("content", "") or ""
    issues = []
    seen = set()

    for match in NAMED_METHOD.finditer(content):
        name = match.group("name").strip()
        normalized = _normalize(name)
        if not normalized or normalized in corpus or normalized in seen:
            continue
        seen.add(normalized)
        context = _context(content, match.start(), match.end())
        if _is_visibly_adapted(context) and normalized in choices:
            continue
        issues.append(
            {
                "code": "unsupported_named_framework_needs_review",
                "severity": "review",
                "message": (
                    f"The output presents {name!r} like a named method or framework, but "
                    "that name is not supported by the brief or retrieved knowledge. "
                    "Remove the source-sounding label or explicitly frame and track it as "
                    "a generator-created label."
                ),
                "name": name,
            }
        )
    return issues


def _unsupported_taxonomy_issues(output: dict, brief: dict, knowledge_snapshot: list[dict]):
    raw_support = "\n".join(_support_strings(brief, knowledge_snapshot))
    raw_choices = _choice_text(output)
    content = output.get("content", "") or ""
    issues = []
    seen = set()

    # Examine sentence-sized spans containing at least three quoted short labels,
    # e.g. 'K', 'S', and 'W'. These often look authoritative despite being
    # invented organizing taxonomies.
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
        matches = list(QUOTED_SHORT_LABEL.finditer(sentence))
        labels = [match.group("label") for match in matches]
        unique = tuple(dict.fromkeys(labels))
        if len(unique) < 3 or unique in seen:
            continue
        seen.add(unique)
        unsupported = [
            label for label in unique
            if f"'{label}'" not in raw_support and f'"{label}"' not in raw_support
        ]
        if len(unsupported) < 2:
            continue
        tracked = all(
            label.lower() in _normalize(raw_choices).split()
            for label in unique
        )
        if _is_visibly_adapted(sentence) and tracked:
            continue
        issues.append(
            {
                "code": "unsupported_taxonomy_needs_review",
                "severity": "review",
                "message": (
                    "The output introduces a short-label taxonomy that is not supported "
                    "by the brief or retrieved knowledge: "
                    + ", ".join(unique)
                    + ". Remove it, or clearly present it as a generator-created labeling "
                    "choice and track that choice."
                ),
                "labels": list(unique),
                "unsupported_labels": unsupported,
            }
        )
    return issues


def grounding_review_issues(output: dict, brief: dict, knowledge_snapshot: list[dict]):
    """Return conservative review issues for unsupported specific-looking claims."""
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

    issues.extend(_unsupported_number_issues(output, brief or {}, knowledge_snapshot or []))
    issues.extend(_unsupported_named_method_issues(output, brief or {}, knowledge_snapshot or []))
    issues.extend(_unsupported_taxonomy_issues(output, brief or {}, knowledge_snapshot or []))
    return issues
