"""Conservative generated-prose integrity gate; not a semantic validator."""
import json
import re

from app.services.performance_timing import emit

DETECTOR = "adjacent-word-periodicity-v1"


class ExtractionValidationError(RuntimeError):
    """A generated response failed local validation before settlement."""


class GeneratedContentIntegrityError(ExtractionValidationError):
    """Safe diagnostics only; deliberately retains no rejected text."""


# Evidence, provenance labels and retrieval keywords are intentionally excluded.
PROSE_FIELDS = (
    "title", "what_it_says", "why_it_matters", "how_to_apply", "when_to_use",
    "when_not_to_use", "tradeoffs", "condition", "action", "rationale",
    "steps", "adaptation_notes", "what_happened", "transferable_lesson",
    "concept_demonstrated", "consequence", "prevention", "components",
)


def measure_periodicity(text):
    text = text or ''
    tokens = re.findall(r'\w+', text.casefold())
    count = len(tokens)
    longest = 0
    period = None
    # O(32*n), including single-word degeneration. Count adjacent cycles rather
    # than common phrases scattered through a valid long document.
    for width in range(1, min(32, count // 2) + 1):
        equal_run = 0
        for index in range(width, count):
            equal_run = equal_run + 1 if tokens[index] == tokens[index-width] else 0
            span = equal_run + width if equal_run else 0
            if span > longest:
                longest, period = span, width
    repeats = longest // period if period else 0
    ratio = longest / count if count else 0
    return {
        'characters': len(text), 'words': count,
        'adjacent_periodic_words': longest, 'period_words': period,
        'complete_cycles': repeats, 'periodic_fraction': ratio,
        'exceptional_length_diagnostic': len(text) > 16384,
        'severe_repetition_signal': count >= 160 and longest >= 128
                                   and repeats >= 8 and ratio >= .60,
    }


def check_generated_assets(assets, job):
    """Check the whole candidate chunk before any settlement side effect."""
    from app.services.numbered_list_review import review_asset
    for index, asset in enumerate(assets):
        reviewed = review_asset(asset)
        # Counts and source quotations do not establish claimed completeness.
        # Keep every numbered-list hint advisory, including explicit mismatches.
        if reviewed:
            emit('generated_content_integrity', result='diagnostic_only',
                 detector='numbered-list-review-v2', job_id=job['id'],
                 source_id=job['source_id'], chunk_id=job['chunk_id'],
                 asset_index=index, signals=reviewed)
        for field in PROSE_FIELDS:
            value = getattr(asset, field, None)
            values = enumerate(value) if isinstance(value, list) else [(None, value)]
            for item_index, text in values:
                if not isinstance(text, str):
                    continue
                metrics = measure_periodicity(text)
                if not (metrics['severe_repetition_signal'] or metrics['exceptional_length_diagnostic']):
                    continue
                path = f"assets[{index}].{field}"
                if item_index is not None:
                    path += f"[{item_index}]"
                diagnostic = dict(detector=DETECTOR, job_id=job['id'],
                                  source_id=job['source_id'], chunk_id=job['chunk_id'],
                                  field_path=path, **metrics)
                if metrics['severe_repetition_signal']:
                    diagnostic['reason'] = 'severe_adjacent_periodic_repetition'
                    emit('generated_content_integrity', result='review_required', **diagnostic)
                    raise GeneratedContentIntegrityError(
                        'Generated content failed an integrity check; review required. '
                        'No candidate assets saved; previous knowledge unchanged. '
                        'No automatic repair or retry. Diagnostics: '
                        + json.dumps(diagnostic, sort_keys=True))
                emit('generated_content_integrity', result='length_diagnostic_only', **diagnostic)
