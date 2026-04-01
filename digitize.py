#!/usr/bin/env python3
"""
Scans a GCS bucket for raw PDFs/images and transcribes them into LaTeX
using Vertex AI Gemini (multimodal). Saves .tex files back to GCS.

Usage:
  python digitize.py                  # process all pending
  python digitize.py --max_files 50   # first 50 pending files
  python digitize.py --dry_run        # list pending, don't call API
"""

import argparse
import json
import mimetypes
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig, Part

from config import (
    PROJECT_ID, REGION, BUCKET_NAME, RAW_PREFIX,
    SUPPORTED_EXTENSIONS, TRANSCRIBE_MODEL_CANDIDATES,
    setup_logging,
)

logger = setup_logging("digitize")

# Ignore junk folders that might exist inside the GCS bucket
SKIP_SUBSTRINGS = [".venv", "__pycache__", ".git"]

# Failed files get logged here so we can retry them later
DEFAULT_REPORT_PATH = "digitize_failures.jsonl"


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

# Represents one raw file (PDF/image) found in GCS that needs digitization
@dataclass
class BlobItem:
    name: str
    gs_uri: str
    content_type: str
    ext: str


# When a file fails all retries, we save this record to the failure report
@dataclass
class FailureRecord:
    blob_name: str
    gs_uri: str
    error: str
    timestamp: str
    attempt: int


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _is_skippable(blob_name: str) -> bool:
    """Skip junk paths like .venv or __pycache__ that aren't real exam files."""
    lower = blob_name.lower()
    return any(s in lower for s in SKIP_SUBSTRINGS)


def _guess_content_type(blob_name: str, blob_ct: Optional[str]) -> str:
    """GCS sometimes stores files as 'application/octet-stream' which Gemini
    can't use — so we fall back to guessing from the file extension."""
    if blob_ct and blob_ct != "application/octet-stream":
        return blob_ct
    mt, _ = mimetypes.guess_type(blob_name)
    return mt or "application/octet-stream"


def _tex_companion_names(raw_name: str) -> list:
    """Check both naming conventions because the scheme changed during development.
    Old: image.tex | New: image.png.tex — need to check both to avoid re-digitizing."""
    stem, _ = os.path.splitext(raw_name)
    return [
        raw_name + ".tex",       # new convention: image.png.tex
        stem + ".tex",           # old convention: image.tex
    ]


def _tex_upload_name(raw_name: str) -> str:
    """Always use new convention for uploads: keeps the original extension visible."""
    return raw_name + ".tex"


def _build_existing_tex_set(bucket: storage.Bucket, prefix: str) -> set:
    """Pre-fetch ALL .tex names in one API call instead of checking one-by-one.
    Why: checking 624 files individually = 624 API calls (slow + expensive).
    Pre-fetching into a set = 1 API call + instant O(1) lookups."""
    logger.info("Building set of existing .tex files (this avoids per-file existence checks)...")
    tex_set = set()
    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name.lower().endswith(".tex"):
            tex_set.add(blob.name)
    logger.info(f"Found {len(tex_set)} existing .tex files")
    return tex_set


# ──────────────────────────────────────────────
# Blob iteration
# ──────────────────────────────────────────────
def iter_pending_blobs(
    bucket: storage.Bucket,
    prefix: str,
    existing_tex: set,
) -> Iterable[BlobItem]:
    """Yields only files that STILL NEED digitization.
    This is the incremental logic: run the script multiple times and it only
    processes new files. Saves money on API calls."""
    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name.endswith("/"):          # skip GCS "directory" markers
            continue
        if _is_skippable(blob.name):
            continue

        ext = os.path.splitext(blob.name)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:  # only PDF, PNG, JPG, etc.
            continue

        # Already has a .tex output? Skip it.
        if any(name in existing_tex for name in _tex_companion_names(blob.name)):
            continue

        ct = _guess_content_type(blob.name, blob.content_type)
        yield BlobItem(
            name=blob.name,
            gs_uri=f"gs://{bucket.name}/{blob.name}",
            content_type=ct,
            ext=ext,
        )


# ──────────────────────────────────────────────
# Transcription prompt
# ──────────────────────────────────────────────

# This prompt is sent to Gemini along with each scanned image.
# Why so specific: generic OCR instructions produce messy output.
# We need Gemini to understand Tunisian math notation and Bac formatting.
# The watermark rule was added after early runs where Gemini transcribed
# teacher signatures and stamps as if they were part of the exercise.
TRANSCRIPTION_PROMPT = r"""
Tu es un professeur tunisien de mathématiques (Baccalauréat section Maths).
Ta tâche : transcrire FIDÈLEMENT le document fourni (énoncé + correction si présent) en LaTeX propre.

CONTRAINTES :
1. Écris en FRANÇAIS académique tunisien.
2. Préserve la rédaction officielle : "On a", "Or", "Donc", "Ainsi", "Par conséquent", "D'après …".
3. TOUTES les expressions mathématiques en LaTeX :
   - Inline : $...$
   - Display : \[ ... \] ou environnement align*, cases, etc.
4. Si une partie est illisible : écris [ILLISIBLE] à cet endroit exact.
5. Conserve l'ORDRE exact du document (énoncé puis correction).
6. NE commente PAS, NE résume PAS. Fournis UNIQUEMENT le LaTeX final.
7. IGNORE complètement tout filigrane, signature d'auteur, logo ou texte en arrière-plan
   (par exemple le nom du professeur, tampon, cachet, ou marque d'eau).
   Ces éléments NE font PAS partie du contenu mathématique — ne les transcris jamais.

FORMAT :
- \section*{Énoncé} en début (si énoncé présent).
- \section*{Correction} si correction présente.
- \subsection*{Exercice N} pour chaque exercice numéroté.
- Environnements propres : align*, cases, enumerate, itemize.
- Numérote les parties comme dans l'original (1), 2), a), b), etc.).
"""


# ──────────────────────────────────────────────
# Model initialization
# ──────────────────────────────────────────────
def _init_vertex():
    vertexai.init(project=PROJECT_ID, location=REGION)


def _pick_model(candidates: List[str]) -> GenerativeModel:
    """Takes a list of model IDs from config, uses the first one.
    Why a list: originally planned fallback to a second model if the first
    was unavailable, but Gemini 2.5 Flash was always available in practice."""
    if not candidates:
        raise ValueError("No model candidates provided")
    model_id = candidates[0]
    logger.info(f"Using transcription model: {model_id}")
    return GenerativeModel(model_id)


# ──────────────────────────────────────────────
# Transcription with retry
# ──────────────────────────────────────────────
def _transcribe_with_retry(
    model: GenerativeModel,
    gs_uri: str,
    content_type: str,
    prompt: str,
    retries: int = 3,
    base_sleep: float = 3.0,
) -> str:
    """Send image + prompt to Gemini, get LaTeX back.
    Why retry with exponential backoff: Gemini API sometimes returns
    transient errors (rate limits, timeouts). Without this, a batch of
    624 files would fail halfway and you'd have to restart manually."""

    # Part.from_uri sends the GCS URI directly to Gemini — no need to
    # download the file to local disk first
    file_part = Part.from_uri(gs_uri, mime_type=content_type)
    last_err = None

    for attempt in range(1, retries + 1):
        try:
            t0 = time.monotonic()
            resp = model.generate_content(
                [prompt, file_part],
                generation_config=GenerationConfig(
                    temperature=0.0,      # deterministic: OCR should be exact, not creative
                    max_output_tokens=8192,  # large enough for full exam pages
                ),
            )
            elapsed = time.monotonic() - t0
            text = (resp.text or "").strip()
            if not text:
                raise RuntimeError("Empty response from model")
            logger.info(f"  Transcription OK ({elapsed:.1f}s, {len(text)} chars)")
            return text
        except Exception as e:
            last_err = e
            sleep_s = base_sleep * (2 ** (attempt - 1))  # exponential: 3s, 6s, 12s
            logger.warning(f"  Attempt {attempt}/{retries} failed: {e}. Sleeping {sleep_s:.0f}s")
            time.sleep(sleep_s)

    raise RuntimeError(f"Failed after {retries} attempts: {last_err}")


# ──────────────────────────────────────────────
# Failure report
# ──────────────────────────────────────────────
def _append_failure(report_path: str, record: FailureRecord):
    """Write failures to JSONL (one JSON per line). Why JSONL: it's append-safe —
    if the script crashes mid-run, records already written are preserved."""
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Digitize PDFs/images to LaTeX via Vertex AI")
    parser.add_argument("--max_files", type=int, default=0,
                        help="Process at most N files (0 = no limit)")
    # --dry_run: see what WOULD be processed without spending money on API calls
    parser.add_argument("--dry_run", action="store_true",
                        help="List pending files without processing")
    parser.add_argument("--report", type=str, default=DEFAULT_REPORT_PATH,
                        help="Path for JSONL failure report")
    parser.add_argument("--retries", type=int, default=3,
                        help="Max retries per file")
    args = parser.parse_args()

    # Connect to Google Cloud Storage
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)

    # Step 1: fetch all existing .tex files in ONE call (not one per file)
    existing_tex = _build_existing_tex_set(bucket, RAW_PREFIX)

    # Step 2: find files that still need digitization
    pending = list(iter_pending_blobs(bucket, RAW_PREFIX, existing_tex))
    if args.max_files:  # --max_files N: useful for testing with a small batch
        pending = pending[:args.max_files]

    logger.info(f"Pending files to digitize: {len(pending)}")

    if args.dry_run:
        for item in pending:
            print(f"  PENDING: {item.name} ({item.content_type})")
        return

    if not pending:
        logger.info("Nothing to do.")
        return

    # Step 3: initialize Gemini model (only if we actually have work to do)
    _init_vertex()
    model = _pick_model(TRANSCRIBE_MODEL_CANDIDATES)

    processed = 0
    failed = 0
    total_start = time.monotonic()

    # Step 4: process each file — send to Gemini, upload the .tex result
    for idx, item in enumerate(pending, 1):
        logger.info(f"[{idx}/{len(pending)}] Digitizing: {item.name}")
        try:
            latex = _transcribe_with_retry(
                model, item.gs_uri, item.content_type,
                TRANSCRIPTION_PROMPT, retries=args.retries,
            )
            # Save result back to GCS alongside the original file
            tex_name = _tex_upload_name(item.name)
            blob = bucket.blob(tex_name)
            blob.upload_from_string(latex, content_type="text/x-tex")
            logger.info(f"  Uploaded: gs://{BUCKET_NAME}/{tex_name}")
            processed += 1

        except Exception as e:
            # Don't crash the whole batch — log the failure and continue
            failed += 1
            logger.error(f"  FAILED: {item.name}: {e}")
            _append_failure(args.report, FailureRecord(
                blob_name=item.name,
                gs_uri=item.gs_uri,
                error=str(e),
                timestamp=datetime.now(timezone.utc).isoformat(),
                attempt=args.retries,
            ))

    elapsed = time.monotonic() - total_start
    logger.info(
        f"Done in {elapsed:.1f}s. "
        f"Processed={processed} | Failed={failed} | "
        f"Already existed={len(existing_tex)}"
    )
    if failed:
        logger.info(f"Failure report: {args.report}")


if __name__ == "__main__":
    main()
