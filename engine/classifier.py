"""Explainable classification bands based on explicit recovery evidence.

Evidence and base confidence:

| Class | Required evidence | Base confidence |
|---|---|---:|
| intact | Directory entry, complete chain or validated contiguity, full validator success | 0.98 live / 0.92 deleted |
| carved | Signature found, contiguous bytes, full validator success, no directory metadata | 0.78 |
| reconstructed | Two fragments joined by bounded search and full validator success | 0.65 |
| partial | At least the configured fraction decodes, but full validation fails | 0.30 + 0.20 * decoded fraction |

Duplicate-looking content, unusually small files, ambiguous endings, expensive
searches, and multiple valid joins reduce confidence within the class band.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from engine.config import PARTIAL_MIN_DECODED_FRACTION


Classification = Literal["intact", "carved", "reconstructed", "partial"]


@dataclass(frozen=True)
class ClassificationResult:
    """A rule-based class, calibrated confidence, and user-facing explanation."""

    classification: Classification
    confidence: float
    reason: str


def classify_file(
    source: str,
    *,
    state: str,
    dir_entry_present: bool,
    validation_ok: bool,
    full_chain: bool,
    decoded_fraction: float = 1.0,
    search_cost: int = 0,
    multiple_joins: int = 1,
    duplicate: bool = False,
    unusually_small: bool = False,
    ambiguous_footer: bool = False,
) -> ClassificationResult:
    """Classify a result from recovery route and directly observed evidence."""
    if not 0 <= decoded_fraction <= 1:
        raise ValueError("decoded_fraction must be between zero and one")
    if search_cost < 0 or multiple_joins < 1:
        raise ValueError("search cost and join count must be non-negative")
    risk_penalty = (
        0.02 * duplicate + 0.015 * unusually_small + 0.02 * ambiguous_footer
    )

    if source == "fat32" and dir_entry_present and validation_ok:
        if state == "live" and full_chain:
            confidence = max(0.95, 0.98 - risk_penalty)
            reason = "Recovered from a live directory entry and its complete allocation; the whole file validates."
        else:
            confidence = max(0.88, min(0.95, 0.92 - risk_penalty))
            reason = "Recovered from a deleted directory entry by assuming its data was contiguous; the whole file validates."
        return ClassificationResult("intact", confidence, reason)

    if source == "fragments" and validation_ok:
        cost_penalty = min(0.12, math.log10(search_cost + 1) * 0.025)
        ambiguity_penalty = min(0.10, (multiple_joins - 1) * 0.03)
        confidence = max(0.50, min(
            0.70, 0.65 - cost_penalty - ambiguity_penalty - risk_penalty
        ))
        reason = "Rebuilt from two validated pieces; the missing gap was inferred from the image."
        return ClassificationResult("reconstructed", confidence, reason)

    if validation_ok:
        confidence = max(0.70, min(0.85, 0.78 - risk_penalty))
        reason = "Found by its file signature; the whole file validates, but its name and dates were not recovered."
        return ClassificationResult("carved", confidence, reason)

    if decoded_fraction < PARTIAL_MIN_DECODED_FRACTION:
        raise ValueError("decoded fraction is below the minimum for a partial result")
    confidence = max(0.30, min(0.49, 0.30 + 0.20 * decoded_fraction - risk_penalty))
    reason = "Only part of the image could be decoded; the file may be incomplete."
    return ClassificationResult("partial", confidence, reason)
