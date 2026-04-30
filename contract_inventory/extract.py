"""LLM extraction for SP7 contracts.

Single-pass structured extraction via ``client.messages.parse()``. The system
prompt is cached so repeated runs across many contracts are cheap. After the
model returns, every quote field is verified against the source text — quotes
that don't appear verbatim are flagged in ``reviewer_notes`` rather than
silently trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import anthropic

from .parse import quote_appears_in
from .schema import ContractExtraction


SYSTEM_PROMPT = """\
You are a meticulous commercial-contract analyst. You extract two specific
areas from SP7 service contracts and return strictly structured JSON.

Areas of interest:

1. Base package vs. Time & Materials (T&M) add-ons
   - What is included in the base package (scope, deliverables)?
   - Which services are explicitly priced as T&M or add-ons?
   - Commercial-risk flags tied to the base package, especially:
     * `lump_sum_warranty`: warranty obligations bundled into the base fee
       with no separate price or hour cap, exposing the supplier to unbounded
       remediation work.
     * `unbounded_scope`: deliverables described with open-ended language
       (\"including but not limited to\", \"as required\", \"reasonable
       efforts\") without a hard cap.
     * `uncapped_liability`: SLA penalties or damages with no stated cap.
     * `open_ended_inclusion`: clauses that fold future work into the base
       fee without a clear boundary.

2. Patch management
   - Is patch management required by the contract?
   - How is it priced: included in the base fee, T&M, fixed fee, other?
   - What does it cover (OS, applications, security only, etc.)?
   - What is the end date or term?

CRITICAL RULES:

- Every non-trivial finding MUST include a `quote` field that is a verbatim
  copy of text from the contract, including punctuation. Do not paraphrase
  inside `quote`. Do not invent text.
- If a field is not addressed by the contract, return null for that field
  and add the dotted field path to `not_found`. NEVER guess, infer, or fill
  a field with plausible-sounding content. Absence is a valid answer.
- `confidence` reflects your overall certainty: `high` if every field has
  clear textual support, `medium` if some fields required interpretation,
  `low` if the contract is ambiguous or incomplete.
- `reviewer_notes` is for genuine ambiguities a human should resolve.

You will be given the contract text wrapped in <contract> tags. Use only
the provided text — do not rely on outside knowledge of the supplier.
"""


@dataclass
class ExtractionResult:
    extraction: ContractExtraction
    invalid_quotes: list[str]
    usage: dict


def extract_contract(
    *,
    client: anthropic.Anthropic,
    contract_id: str,
    contract_text: str,
    model: str = "claude-opus-4-7",
    effort: str = "high",
) -> ExtractionResult:
    """Extract the schema from one contract."""
    user_content = (
        f"Contract identifier: {contract_id}\n\n"
        f"<contract>\n{contract_text}\n</contract>\n\n"
        "Extract the schema. Set `contract_id` to the identifier above."
    )

    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_format=ContractExtraction,
    )

    extraction: ContractExtraction = response.parsed_output

    invalid = _verify_quotes(extraction, contract_text)
    if invalid:
        note_prefix = "QUOTE VERIFICATION FAILED for: " + ", ".join(invalid)
        existing = extraction.reviewer_notes or ""
        extraction.reviewer_notes = (
            f"{note_prefix}. {existing}".strip() if existing else note_prefix
        )

    return ExtractionResult(
        extraction=extraction,
        invalid_quotes=invalid,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", 0
            ),
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0
            ),
        },
    )


def _verify_quotes(extraction: ContractExtraction, source: str) -> list[str]:
    """Return a list of dotted field paths whose quotes don't appear in source."""
    invalid: list[str] = []

    def check(path: str, quote: Optional[str]) -> None:
        if quote and not quote_appears_in(quote, source):
            invalid.append(path)

    check("base_package.definition_quote", extraction.base_package.definition_quote)

    for i, addon in enumerate(extraction.tm_addons):
        check(f"tm_addons[{i}].quote", addon.quote)

    for i, flag in enumerate(extraction.commercial_risk_flags):
        check(f"commercial_risk_flags[{i}].evidence_quote", flag.evidence_quote)

    check("patch_management.evidence_quote", extraction.patch_management.evidence_quote)

    return invalid
