"""DESIGN PROBE ONLY. Not imported by the app; not a validator or acceptance gate.

Measurements test a conservative candidate signal, not semantic truth. In
particular, intentional quotations may have the same periodicity as corruption.
Thresholds are proposals requiring review, not settled product requirements.
"""
import re


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
