"""SP7 contract inventory MVP — CLI entry point.

Usage:

    export ANTHROPIC_API_KEY=...
    python -m contract_inventory.main \\
        --input ./contracts \\
        --output ./sp7_inventory.xlsx \\
        --family-mode per-file        # or per-folder for multi-file contracts

Outputs alongside ``--output``:
  - ``<output>.xlsx``                — Excel workbook (Inventory + Evidence)
  - ``<output_stem>_json/*.json``    — one JSON snapshot per contract family
  - ``<output_stem>.run.log``        — full processing log
  - ``<output_stem>.run_summary.csv`` — one row per family with status
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

import anthropic

from .extract import extract_contract
from .export import write_excel
from .family import resolve_families
from .schema import ContractExtraction


RUN_SUMMARY_HEADERS = [
    "family_id",
    "status",          # ok | needs_review | failed | skipped
    "files",
    "confidence",
    "risk_count",
    "patch_required",
    "validation_warnings",
    "error",
    "json_path",
]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_dir = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_dir = output_path.parent / f"{output_path.stem}_json"
    json_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_path.parent / f"{output_path.stem}.run.log"
    summary_path = output_path.parent / f"{output_path.stem}.run_summary.csv"

    logger = _setup_logging(log_path)
    logger.info("Run started at %s", datetime.utcnow().isoformat() + "Z")
    logger.info("Input: %s | Output: %s | Family mode: %s",
                input_dir, output_path, args.family_mode)

    families = resolve_families(input_dir, args.family_mode)
    if not families:
        logger.error("No supported contract files found in %s", input_dir)
        return 1
    logger.info("Resolved %d contract famil%s",
                len(families), "y" if len(families) == 1 else "ies")

    client = anthropic.Anthropic()
    extractions: list[ContractExtraction] = []
    summary_rows: list[dict] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0,
                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}

    for i, family in enumerate(families, start=1):
        logger.info("[%d/%d] %s — %d file(s)",
                    i, len(families), family.family_id, len(family.files))
        text, files_used, parse_warnings = family.combined_text()
        for w in parse_warnings:
            logger.warning("  parse: %s", w)
        if not files_used:
            summary_rows.append(_summary_row(
                family_id=family.family_id, status="skipped",
                files=family.files, error="no readable files",
                warnings=parse_warnings,
            ))
            continue

        try:
            result = extract_contract(
                client=client,
                contract_id=family.family_id,
                contract_text=text,
                source_files=[str(p) for p in files_used],
                model=args.model,
                effort=args.effort,
            )
        except Exception as e:
            logger.error("  extraction failed: %s", e)
            logger.debug(traceback.format_exc())
            summary_rows.append(_summary_row(
                family_id=family.family_id, status="failed",
                files=files_used, error=str(e),
                warnings=parse_warnings,
            ))
            continue

        extractions.append(result.extraction)
        for k, v in result.usage.items():
            total_usage[k] = total_usage.get(k, 0) + v

        json_path = json_dir / f"{family.family_id}.json"
        json_path.write_text(
            result.extraction.model_dump_json(indent=2), encoding="utf-8"
        )

        status = "needs_review" if result.extraction.review_required else "ok"
        warnings_combined = list(parse_warnings) + list(result.extraction.validation_warnings)

        logger.info(
            "  %s: confidence=%s, risks=%d, invalid_quotes=%d, warnings=%d",
            status,
            result.extraction.confidence.value,
            len(result.extraction.commercial_risk_flags),
            len(result.invalid_quotes),
            len(result.extraction.validation_warnings),
        )
        for w in result.extraction.validation_warnings:
            logger.info("    warning: %s", w)

        summary_rows.append(_summary_row(
            family_id=family.family_id, status=status,
            files=files_used, error=None,
            warnings=warnings_combined,
            extraction=result.extraction,
            json_path=json_path,
        ))

    if not extractions:
        logger.error("No contracts extracted.")
        _write_summary(summary_path, summary_rows)
        return 1

    write_excel(extractions, output_path)
    _write_summary(summary_path, summary_rows)

    logger.info("Wrote %s (%d contracts)", output_path, len(extractions))
    logger.info("Wrote %s", summary_path)
    logger.info("Token usage: %s", total_usage)
    needs_review = sum(1 for e in extractions if e.review_required)
    logger.info("Review required for %d/%d contracts", needs_review, len(extractions))
    return 0


def _summary_row(*, family_id: str, status: str, files,
                 error: str | None = None, warnings: list[str] | None = None,
                 extraction: ContractExtraction | None = None,
                 json_path: Path | None = None) -> dict:
    return {
        "family_id": family_id,
        "status": status,
        "files": "; ".join(Path(p).name for p in files),
        "confidence": extraction.confidence.value if extraction else "",
        "risk_count": len(extraction.commercial_risk_flags) if extraction else "",
        "patch_required":
            ("yes" if extraction.patch_management.required else "no")
            if extraction and extraction.patch_management.required is not None else "",
        "validation_warnings": " | ".join(warnings or []),
        "error": error or "",
        "json_path": str(json_path) if json_path else "",
    }


def _write_summary(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_SUMMARY_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def _setup_logging(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("contract_inventory")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


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
    p.add_argument(
        "--family-mode",
        default="per-file",
        choices=["per-file", "per-folder"],
        help=(
            "How to group input files into contracts. "
            "per-file: each file is one contract (default). "
            "per-folder: each immediate subdirectory of --input is one contract "
            "(loose root files remain per-file)."
        ),
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
