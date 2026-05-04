"""Deterministic post-extraction validation.

Quote verification (in extract.py) catches fabricated text. This catches
*logical* gaps the model can produce despite valid quotes:

  - "patch_required = true" with no scope, pricing, or evidence quote
  - a risk flag with no evidence quote
  - "end_date" set but unparseable as a date
  - "confidence = low" → always review_required
  - any quote that failed verification → always review_required

Each rule appends a short string to ``validation_warnings`` and may set
``review_required = True``. Output is reviewer-actionable, not a score.
"""

from __future__ import annotations

import re
from typing import Optional

from .schema import ContractExtraction, Confidence, PricingModel


# Reasonable date formats seen in contracts. We don't normalize; we just
# check that *something* parses, so we know the model isn't returning junk.
_DATE_PATTERNS = [
    r"^\d{4}-\d{2}-\d{2}$",                             # 2027-12-31
    r"^\d{1,2}/\d{1,2}/\d{2,4}$",                       # 31/12/2027
    r"^\d{1,2}\.\d{1,2}\.\d{2,4}$",                     # 31.12.2027
    r"^\d{1,2}\s+[A-Za-z]+\s+\d{4}$",                   # 31 December 2027
    r"^[A-Za-z]+\s+\d{1,2},?\s+\d{4}$",                 # December 31, 2027
    r"^\d{4}$",                                          # 2027 (year only)
]
_DATE_REGEX = [re.compile(p) for p in _DATE_PATTERNS]


def _parses_as_date(value: str) -> bool:
    return any(rx.match(value.strip()) for rx in _DATE_REGEX)


def validate(extraction: ContractExtraction, invalid_quote_paths: list[str]) -> None:
    """Mutate ``extraction`` in place — set ``review_required`` and append warnings."""
    warnings: list[str] = []
    review = False

    # Rule 1: any quote that failed verification → review.
    if invalid_quote_paths:
        warnings.append(
            "quote_verification_failed: " + ", ".join(invalid_quote_paths)
        )
        review = True

    # Rule 2: confidence=low → always review.
    if extraction.confidence == Confidence.low:
        warnings.append("low_confidence: model self-reported low confidence")
        review = True

    # Rule 3: patch_management.required=true must have supporting evidence.
    pm = extraction.patch_management
    if pm.required is True:
        missing: list[str] = []
        if not pm.evidence_quote:
            missing.append("evidence_quote")
        if pm.pricing_model == PricingModel.not_specified:
            missing.append("pricing_model")
        if not pm.scope_summary:
            missing.append("scope_summary")
        if missing:
            warnings.append(
                "patch_required_without_support: missing " + ", ".join(missing)
            )
            review = True

    # Rule 4: end_date present but doesn't parse as a date.
    if pm.end_date and not _parses_as_date(pm.end_date):
        warnings.append(f"unparseable_end_date: {pm.end_date!r}")
        review = True

    # Rule 5: every commercial-risk flag must have an evidence quote.
    for i, flag in enumerate(extraction.commercial_risk_flags):
        if not flag.evidence_quote.strip():
            warnings.append(f"risk_flag_without_evidence: index={i}, type={flag.risk_type.value}")
            review = True

    # Rule 6: page resolution failed for any field that has a quote.
    unresolved = _unresolved_pages(extraction)
    if unresolved:
        warnings.append("unresolved_pages: " + ", ".join(unresolved))
        # Don't auto-review — page resolution can fail on plain-text contracts
        # (no [[PAGE n]] markers). Reviewer can decide.

    # Rule 7: not_found should not contain fields that *are* populated.
    contradictions = _not_found_contradictions(extraction)
    if contradictions:
        warnings.append("not_found_contradicts_extraction: " + ", ".join(contradictions))
        review = True

    extraction.validation_warnings = warnings
    extraction.review_required = review or extraction.review_required


def _unresolved_pages(e: ContractExtraction) -> list[str]:
    paths: list[str] = []
    if e.base_package.definition_quote and e.base_package.source_page is None:
        paths.append("base_package")
    for i, addon in enumerate(e.tm_addons):
        if addon.quote and addon.source_page is None:
            paths.append(f"tm_addons[{i}]")
    for i, flag in enumerate(e.commercial_risk_flags):
        if flag.evidence_quote and flag.source_page is None:
            paths.append(f"commercial_risk_flags[{i}]")
    if e.patch_management.evidence_quote and e.patch_management.source_page is None:
        paths.append("patch_management")
    return paths


def _not_found_contradictions(e: ContractExtraction) -> list[str]:
    contradictions: list[str] = []
    populated = {
        "base_package.definition_quote": bool(e.base_package.definition_quote),
        "patch_management.required": e.patch_management.required is not None,
        "patch_management.end_date": bool(e.patch_management.end_date),
        "patch_management.evidence_quote": bool(e.patch_management.evidence_quote),
    }
    for path in e.not_found:
        if populated.get(path):
            contradictions.append(path)
    return contradictions
