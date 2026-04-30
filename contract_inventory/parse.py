"""Document parsing for SP7 contracts.

Native text first (PyMuPDF / python-docx); plain text passthrough for `.txt`.
OCR is intentionally not in the MVP — add it once we know real contracts need it.
"""

from __future__ import annotations

from pathlib import Path


class UnsupportedFormatError(Exception):
    pass


def parse_document(path: Path) -> str:
    """Return the full text of a contract file.

    Supports .pdf, .docx, .txt, .md.
    """
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
    """Normalize whitespace and curly quotes so quote verification is robust."""
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
    """Check whether `quote` appears in `source` after whitespace/punctuation normalization."""
    if not quote:
        return False
    return normalize_quote(quote) in normalize_quote(source)
