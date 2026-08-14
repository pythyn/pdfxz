from __future__ import annotations

from pathlib import Path

import pytest

FAKE_GS_PATH = str(Path(__file__).parent / "fixtures" / "fake_gs.py")

# A minimal-but-plausible PDF body so signature checks and "file size" math
# have something realistic to work with.
VALID_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n"
    b"%%EOF\n"
) * 20  # pad it out so "half the size" style fake compression is meaningful

INVALID_PDF_BYTES = b"This is not a real PDF file, just plain text.\n" * 5


@pytest.fixture()
def make_pdf(tmp_path: Path):
    """Factory fixture: make_pdf('name.pdf') -> Path, with a valid %PDF- header."""

    def _make(
        name: str = "input.pdf",
        content: bytes = VALID_PDF_BYTES,
        directory: Path | None = None,
    ) -> Path:
        target_dir = directory if directory is not None else tmp_path
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / name
        path.write_bytes(content)
        return path

    return _make


@pytest.fixture()
def mock_gs(monkeypatch):
    """Point pdfxz's Ghostscript discovery at the fake gs binary.

    Also resets FAKE_GS_MODE to 'success' for a clean default per test.
    """
    monkeypatch.setenv("FAKE_GS_MODE", "success")
    monkeypatch.setattr(
        "pdfxz.compressor.locate_ghostscript", lambda explicit_path=None: FAKE_GS_PATH
    )
    return FAKE_GS_PATH


@pytest.fixture()
def no_gs(monkeypatch):
    """Simulate Ghostscript being entirely absent from PATH."""
    monkeypatch.setattr(
        "pdfxz.compressor.locate_ghostscript", lambda explicit_path=None: None
    )
