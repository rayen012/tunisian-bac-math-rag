"""Contract-family resolution.

Old SP7 contracts often span a main agreement plus amendments / supplements /
pricing appendices. Processing each file independently produces contradictory
rows. The lightest viable fix: group files into families and feed each family
to the model as a single concatenated document with file-boundary markers.

Two modes:

  - ``per-file``   (default): each file is its own family. Backwards-compatible.
  - ``per-folder``: each immediate subdirectory of the input root is one
                    family. Drop loose files in the root for single-file
                    contracts; group multi-file contracts into a folder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .parse import UnsupportedFormatError, parse_document


SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


@dataclass
class ContractFamily:
    family_id: str
    files: list[Path] = field(default_factory=list)

    def combined_text(self) -> tuple[str, list[Path], list[str]]:
        """Return (combined_text, files_used, parse_warnings)."""
        parts: list[str] = []
        files_used: list[Path] = []
        warnings: list[str] = []
        for path in self.files:
            try:
                text = parse_document(path)
            except UnsupportedFormatError as e:
                warnings.append(f"unsupported: {path.name} ({e})")
                continue
            except Exception as e:  # pragma: no cover — defensive
                warnings.append(f"parse_error: {path.name} ({e})")
                continue
            if not text.strip():
                warnings.append(f"empty: {path.name} (likely scanned PDF — OCR not in MVP)")
                continue
            # File-boundary marker — parse.find_file_for_quote relies on this format.
            parts.append(f"\n=== FILE: {path.name} | {path} ===\n")
            parts.append(text)
            files_used.append(path)
        return "".join(parts), files_used, warnings


def resolve_families(input_dir: Path, mode: str) -> list[ContractFamily]:
    """Walk ``input_dir`` and return contract families per ``mode``."""
    if mode == "per-file":
        return _per_file(input_dir)
    if mode == "per-folder":
        return _per_folder(input_dir)
    raise ValueError(f"Unknown family-mode: {mode}")


def _per_file(input_dir: Path) -> list[ContractFamily]:
    families: list[ContractFamily] = []
    for path in _supported_files(input_dir.rglob("*")):
        families.append(ContractFamily(family_id=path.stem, files=[path]))
    families.sort(key=lambda f: f.family_id)
    return families


def _per_folder(input_dir: Path) -> list[ContractFamily]:
    families: list[ContractFamily] = []

    # Loose files in the root → one family each (mirror per-file)
    root_files = sorted(p for p in input_dir.iterdir()
                        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    for path in root_files:
        families.append(ContractFamily(family_id=path.stem, files=[path]))

    # Each subdirectory is one family
    for subdir in sorted(p for p in input_dir.iterdir() if p.is_dir()):
        files = sorted(_supported_files(subdir.rglob("*")))
        if files:
            families.append(ContractFamily(family_id=subdir.name, files=files))

    return families


def _supported_files(paths: Iterable[Path]) -> list[Path]:
    return [p for p in paths if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES]
