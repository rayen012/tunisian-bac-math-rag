"""Extraction schema for the SP7 contract MVP.

Two questions only — base package / T&M with commercial-risk flags, and patch
management. Every non-trivial field carries a verbatim ``quote`` so the
extraction can be verified against the source text after the LLM call.

Page numbers and source-file attribution are populated deterministically
after the model returns by finding each quote in the marked-up source — the
model is not trusted to count pages.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RiskType(str, Enum):
    lump_sum_warranty = "lump_sum_warranty"
    unbounded_scope = "unbounded_scope"
    uncapped_liability = "uncapped_liability"
    open_ended_inclusion = "open_ended_inclusion"
    other = "other"


class PricingModel(str, Enum):
    included = "included"
    time_and_materials = "time_and_materials"
    fixed_fee = "fixed_fee"
    not_specified = "not_specified"
    other = "other"


class TMAddon(BaseModel):
    service: str = Field(description="Short name of the T&M service or add-on.")
    rate_card_ref: Optional[str] = Field(
        default=None,
        description="Reference to the rate card or pricing schedule, if cited.",
    )
    quote: str = Field(description="Verbatim quote from the contract.")
    source_section: Optional[str] = Field(
        default=None, description="Section, schedule, or clause reference."
    )
    source_page: Optional[int] = Field(
        default=None,
        description="1-based page number. Populated post-extraction; do not set.",
    )
    source_file: Optional[str] = Field(
        default=None,
        description="Source file name (multi-file families). Populated post-extraction.",
    )


class CommercialRiskFlag(BaseModel):
    risk_type: RiskType
    evidence_quote: str = Field(description="Verbatim quote from the contract.")
    source_section: Optional[str] = None
    source_page: Optional[int] = None
    source_file: Optional[str] = None
    severity: Severity
    rationale: str = Field(
        description="One-sentence explanation of why this is a commercial risk."
    )


class BasePackage(BaseModel):
    definition_quote: Optional[str] = Field(
        default=None,
        description="Verbatim quote defining the base package scope. None if absent.",
    )
    source_section: Optional[str] = None
    source_page: Optional[int] = None
    source_file: Optional[str] = None
    scope_summary: Optional[str] = Field(
        default=None,
        description="Plain-language summary of what the base package covers.",
    )


class PatchManagement(BaseModel):
    required: Optional[bool] = Field(
        default=None,
        description="True if the contract requires patch management; None if not addressed.",
    )
    pricing_model: PricingModel = PricingModel.not_specified
    scope_summary: Optional[str] = Field(
        default=None,
        description="What the patch management actually covers (OS patches, app patches, security only, etc.).",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="ISO date or quoted date string for when patch management ends. None if absent.",
    )
    evidence_quote: Optional[str] = Field(
        default=None, description="Verbatim quote from the contract."
    )
    source_section: Optional[str] = None
    source_page: Optional[int] = None
    source_file: Optional[str] = None


class ContractExtraction(BaseModel):
    """Top-level extraction result for one contract (which may span multiple files)."""

    contract_id: str = Field(description="Identifier supplied by the caller (folder or file stem).")

    base_package: BasePackage
    tm_addons: List[TMAddon] = Field(
        default_factory=list,
        description="T&M services or add-ons listed in the contract. Empty if none.",
    )
    commercial_risk_flags: List[CommercialRiskFlag] = Field(
        default_factory=list,
        description="Commercial-risk findings tied to the base package.",
    )

    patch_management: PatchManagement

    confidence: Confidence = Field(
        description="Overall confidence in this extraction."
    )
    not_found: List[str] = Field(
        default_factory=list,
        description="Field paths the contract genuinely does not address (e.g. 'patch_management.end_date').",
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Anything a human reviewer should know — ambiguities, conflicting clauses, OCR artifacts.",
    )

    # ----- Populated post-extraction (not produced by the model) -----
    source_files: List[str] = Field(
        default_factory=list,
        description="File paths that contributed to this extraction. Populated post-extraction.",
    )
    review_required: bool = Field(
        default=False,
        description="True if validation rules say a human must review this row.",
    )
    validation_warnings: List[str] = Field(
        default_factory=list,
        description="Deterministic validation findings (missing evidence, unparseable date, etc.).",
    )
