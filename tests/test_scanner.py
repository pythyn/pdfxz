from __future__ import annotations

import os

from conftest import INVALID_PDF_BYTES, VALID_PDF_BYTES

from pdfxz.scanner import discover_pdfs, validate_pdf


class TestValidatePdf:
    def test_valid_pdf(self, make_pdf):
        path = make_pdf("good.pdf")
        result = validate_pdf(path)
        assert result.ok is True
        assert result.reason is None

    def test_missing_file(self, tmp_path):
        result = validate_pdf(tmp_path / "does_not_exist.pdf")
        assert result.ok is False
        assert "does not exist" in result.reason

    def test_invalid_signature(self, make_pdf):
        path = make_pdf("fake.pdf", content=INVALID_PDF_BYTES)
        result = validate_pdf(path)
        assert result.ok is False
        assert "not a valid PDF" in result.reason

    def test_empty_file(self, make_pdf):
        path = make_pdf("empty.pdf", content=b"")
        result = validate_pdf(path)
        assert result.ok is False

    def test_directory_is_not_a_valid_file(self, tmp_path):
        d = tmp_path / "looks_like.pdf"
        d.mkdir()
        result = validate_pdf(d)
        assert result.ok is False
        assert "regular file" in result.reason

    def test_unreadable_file(self, make_pdf, monkeypatch):
        path = make_pdf("locked.pdf")

        def fake_access(p, mode):
            return False

        monkeypatch.setattr(os, "access", fake_access)
        result = validate_pdf(path)
        assert result.ok is False
        assert "not readable" in result.reason

    def test_does_not_trust_extension_alone(self, make_pdf):
        # .pdf extension but bad content should still fail validation.
        path = make_pdf("trustme.pdf", content=b"not a pdf at all")
        assert validate_pdf(path).ok is False


class TestDiscoverPdfs:
    def test_single_valid_pdf_file(self, make_pdf):
        path = make_pdf("solo.pdf")
        assert discover_pdfs(path) == [path]

    def test_single_non_pdf_file_returns_empty(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("hello")
        assert discover_pdfs(path) == []

    def test_empty_directory(self, tmp_path):
        assert discover_pdfs(tmp_path) == []

    def test_missing_path_returns_empty(self, tmp_path):
        assert discover_pdfs(tmp_path / "nope") == []

    def test_top_level_only_by_default(self, make_pdf, tmp_path):
        top = make_pdf("top.pdf")
        make_pdf("nested.pdf", directory=tmp_path / "sub")
        found = discover_pdfs(tmp_path, recursive=False)
        assert found == [top]

    def test_recursive_discovery(self, make_pdf, tmp_path):
        top = make_pdf("top.pdf")
        nested = make_pdf("nested.pdf", directory=tmp_path / "sub")
        deeper = make_pdf("deeper.pdf", directory=tmp_path / "sub" / "sub2")
        found = discover_pdfs(tmp_path, recursive=True)
        assert set(found) == {top, nested, deeper}

    def test_case_insensitive_extension(self, tmp_path):
        names = ["paper.pdf", "PAPER2.PDF", "Paper3.Pdf"]
        for name in names:
            (tmp_path / name).write_bytes(VALID_PDF_BYTES)
        found = discover_pdfs(tmp_path, recursive=False)
        assert len(found) == 3

    def test_ignores_non_pdf_files(self, make_pdf, tmp_path):
        make_pdf("real.pdf")
        (tmp_path / "readme.txt").write_text("not a pdf")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        found = discover_pdfs(tmp_path, recursive=False)
        assert len(found) == 1
        assert found[0].name == "real.pdf"

    def test_directory_named_dot_pdf_is_ignored(self, tmp_path):
        (tmp_path / "archive.pdf").mkdir()
        found = discover_pdfs(tmp_path, recursive=False)
        assert found == []

    def test_results_are_sorted(self, tmp_path):
        for name in ["c.pdf", "a.pdf", "b.pdf"]:
            (tmp_path / name).write_bytes(VALID_PDF_BYTES)
        found = discover_pdfs(tmp_path, recursive=False)
        assert [p.name for p in found] == ["a.pdf", "b.pdf", "c.pdf"]
