"""Document parsing for SP7 contracts.

Native text first (PyMuPDF / python-docx); plain text passthrough for `.txt`.
OCR is intentionally not in the MVP — add it once we know real contracts need it.

The parsed text contains marker tokens that downstream code uses to derive
page numbers and file attribution post-extraction:

  ``=== FILE: <name> | <path> ===``  marks a file boundary in a multi-file family
  ``[[PAGE n]]``                     marks the start of page n in a PDF
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


PAGE_MARKER = re.compile(r"\[\[PAGE (\d+)\]\]")
FILE_MARKER = re.compile(r"=== FILE: ([^|]+) \| ([^=]+) ===")


class UnsupportedFormatError(Exception):
    pass


def parse_document(path: Path) -> str:
    """Return the full text of a contract file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix == ".docx":
        return _parse_docx(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise UnsupportedFormatError(f"Unsupported file type: {suffix} ({path})")


def _parse_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            parts.append(f"\n[[PAGE {i}]]\n")
            parts.append(page.get_text("text"))
    return "".join(parts)


def _parse_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs if p.text)


def normalize_quote(text: str) -> str:
    """Normalize whitespace, curly quotes and dashes for tolerant matching."""
    replacements = {
        "‘": "'", "’": "'",
        "“": '"', "”": '"',
        "–": "-", "—": "-",
        "\xa0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def quote_appears_in(quote: str, source: str) -> bool:
    if not quote:
        return False
    return normalize_quote(quote) in normalize_quote(source)


def find_quote_offset(quote: str, source: str) -> Optional[int]:
    """Return the offset in `source` where `quote` first appears, or None.

    Match is whitespace-tolerant: we walk the source character by character
    and compare against the normalized quote, skipping runs of whitespace
    and the marker tokens. Returns the offset in the *original* source.
    """
    if not quote:
        return None
    norm_quote = normalize_quote(quote)
    if not norm_quote:
        return None

    norm_source = normalize_quote(source)
    pos = norm_source.find(norm_quote)
    if pos == -1:
        return None

    # Map the position in the normalized string back to the original source.
    # Walk both strings in parallel.
    orig_idx = 0
    norm_idx = 0
    while norm_idx < pos and orig_idx < len(source):
        ch = source[orig_idx]
        # Apply the same normalization rules as normalize_quote
        if ch in "‘’":
            norm_idx += 1
            orig_idx += 1
        elif ch in "“”":
            norm_idx += 1
            orig_idx += 1
        elif ch in "–—":
            norm_idx += 1
            orig_idx += 1
        elif ch == "\xa0":
            # treated as space
            if norm_idx < len(norm_source) and norm_source[norm_idx] == " ":
                norm_idx += 1
            orig_idx += 1
        elif ch.isspace():
            # Whitespace runs collapse to a single space
            if norm_idx < len(norm_source) and norm_source[norm_idx] == " ":
                norm_idx += 1
            orig_idx += 1
            while orig_idx < len(source) and source[orig_idx].isspace():
                orig_idx += 1
        else:
            norm_idx += 1
            orig_idx += 1
    return orig_idx


def find_page_for_quote(quote: str, source: str) -> Optional[int]:
    """Find the PDF page number for a quote, by walking back to the nearest [[PAGE n]] marker."""
    offset = find_quote_offset(quote, source)
    if offset is None:
        return None
    prefix = source[:offset]
    matches = list(PAGE_MARKER.finditer(prefix))
    if not matches:
        return None
    return int(matches[-1].group(1))


def find_file_for_quote(quote: str, source: str) -> Optional[str]:
    """Find the source filename for a quote, by walking back to the nearest === FILE === marker."""
    offset = find_quote_offset(quote, source)
    if offset is None:
        return None
    prefix = source[:offset]
    matches = list(FILE_MARKER.finditer(prefix))
    if not matches:
        return None
    return matches[-1].group(1).strip()
