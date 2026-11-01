"""Metric formulas used by the ForensicRecover scorer."""

from __future__ import annotations

from collections.abc import Iterable


def ratio(numerator: int | float, denominator: int | float) -> float:
    """Return a zero-safe ratio in the unit interval."""
    return min(1.0, numerator / denominator) if denominator else 0.0


def precision(true_positives: int, false_positives: int) -> float:
    """Precision = true positives / all classified recovery items."""
    return ratio(true_positives, true_positives + false_positives)


def recall(exact_matches: int, expected: int) -> float:
    """Recall = exact matches / recoverable ground-truth files."""
    return ratio(exact_matches, expected)


def completeness(values: Iterable[float], expected: int) -> float:
    """Mean per-file matching-block completeness, with misses represented as zero."""
    values = list(values)
    return sum(values) / expected if expected else 0.0


def false_positive_rate(false_positives: int, recovered_items: int) -> float:
    """False-positive rate = false-positive items / all recovered items."""
    return ratio(false_positives, recovered_items)
