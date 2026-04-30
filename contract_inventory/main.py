"""SP7 contract inventory MVP — CLI entry point.

Usage:

    export ANTHROPIC_API_KEY=...
    python -m contract_inventory.main \\
        --input ./contracts \\
        --output ./sp7_inventory.xlsx

The script walks the input directory, extracts the schema from every
supported file, and writes a two-tab Excel workbook (Inventory + Evidence).
JSON snapshots of each extraction are also written next to the workbook so
you can re-run the export step without re-calling the model.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import anthropic

from .extract import extract_contract
from .export import write_excel
from .parse import UnsupportedFormatError, parse_document
from .schema import ContractExtraction


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_dir = Path(args.input)
    output_path = Path(args.output)
    json_dir = output_path.parent / f"{output_path.stem}_json"
    json_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        print(f"No supported contract files found in {input_dir}", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()

    extractions: list[ContractExtraction] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0,
                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}

    for path in files:
        contract_id = path.stem
        print(f"[{len(extractions) + 1}/{len(files)}] {contract_id} ...", flush=True)
        try:
            text = parse_document(path)
        except UnsupportedFormatError as e:
            print(f"  skip: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"  parse error: {e}", file=sys.stderr)
            continue

        if not text.strip():
            print("  skip: empty document (likely scanned PDF — OCR not in MVP)",
                  file=sys.stderr)
            continue

        try:
            result = extract_contract(
                client=client,
                contract_id=contract_id,
                contract_text=text,
                model=args.model,
                effort=args.effort,
            )
        except Exception as e:
            print(f"  extraction error: {e}", file=sys.stderr)
            traceback.print_exc()
            continue

        extractions.append(result.extraction)
        for k, v in result.usage.items():
            total_usage[k] = total_usage.get(k, 0) + v

        json_path = json_dir / f"{contract_id}.json"
        json_path.write_text(
            result.extraction.model_dump_json(indent=2), encoding="utf-8"
        )

        flags = len(result.extraction.commercial_risk_flags)
        confidence = result.extraction.confidence.value
        invalid = len(result.invalid_quotes)
        print(f"  ok: confidence={confidence}, risks={flags}, invalid_quotes={invalid}")

    if not extractions:
        print("No contracts extracted.", file=sys.stderr)
        return 1

    write_excel(extractions, output_path)
    print(f"\nWrote {output_path} ({len(extractions)} contracts)")
    print(f"Token usage: {total_usage}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SP7 contract inventory MVP")
    p.add_argument("--input", required=True, help="Directory of contract files")
    p.add_argument("--output", required=True, help="Output .xlsx path")
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument(
        "--effort",
        default="high",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="Effort level for the extraction (Opus 4.7 default: high).",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
