"""Input discovery and validation.

The scanner has no knowledge of Ghostscript or compression - it only
answers two questions: "which files look like PDF candidates?" and "is
this particular file actually a valid, readable PDF?".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PDF_MAGIC = b"%PDF-"


@dataclass(slots=True)
class ValidationResult:
    """Outcome of validating a single candidate file as a real PDF."""

    ok: bool
    reason: str | None = None


def validate_pdf(path: Path) -> ValidationResult:
    """Validate that `path` exists, is a readable regular file, and begins
    with the PDF signature. Extension is not trusted on its own - the
    magic header is always checked.
    """
    if not path.exists():
        return ValidationResult(False, f"File does not exist: {path}")
    if not path.is_file():
        return ValidationResult(False, f"Not a regular file: {path}")

    try:
        readable = os.access(path, os.R_OK)
    except OSError:
        readable = False
    if not readable:
        return ValidationResult(False, f"File is not readable: {path}")

    try:
        with path.open("rb") as pdf_file:
            header = pdf_file.read(len(PDF_MAGIC))
    except OSError as exc:
        return ValidationResult(False, f"Could not read file: {exc}")

    if header != PDF_MAGIC:
        return ValidationResult(
            False, f"'{path.name}' is not a valid PDF file (missing %PDF- signature)."
        )

    return ValidationResult(True)


def discover_pdfs(root: Path, recursive: bool = False) -> list[Path]:
    """Discover candidate PDF files under `root`.

    `root` may be:
      - a single file: returned as a one-item list if its extension is
        ``.pdf`` (case-insensitive), otherwise an empty list.
      - a directory: PDFs are discovered by extension (case-insensitive).
        Non-recursive mode only inspects direct children; recursive mode
        walks subdirectories. Directories that merely have a ``.pdf`` name
        (e.g. ``archive.pdf/``) are correctly ignored, since they are not
        regular files.

    Discovery is extension-based only; full signature validation happens
    separately via `validate_pdf`, so invalid files are reported per-file
    downstream rather than silently dropped during discovery.
    """
    if root.is_file():
        return [root] if root.suffix.lower() == ".pdf" else []

    if not root.is_dir():
        return []

    entries = root.rglob("*") if recursive else root.iterdir()
    found = [
        entry for entry in entries if entry.is_file() and entry.suffix.lower() == ".pdf"
    ]
    return sorted(found)
