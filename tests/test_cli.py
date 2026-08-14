from __future__ import annotations

import pytest

from pdfxz import __version__
from pdfxz.cli import main


class TestHelpAndVersion:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "usage: pdfxz" in out

    def test_version_exits_zero_and_prints_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert __version__ in out


class TestArgumentValidation:
    def test_no_tui_without_input_errors(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--no-tui"])
        assert exc.value.code == 2

    def test_output_positional_and_flag_conflict_errors(self, tmp_path, capsys):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        with pytest.raises(SystemExit) as exc:
            main([str(pdf), "positional-out.pdf", "-o", "flag-out.pdf"])
        assert exc.value.code == 2

    def test_invalid_quality_choice_errors(self, tmp_path):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        with pytest.raises(SystemExit) as exc:
            main([str(pdf), "-q", "ultra-mega"])
        assert exc.value.code == 2


class TestMissingGhostscript:
    def test_reports_missing_ghostscript_clearly(self, no_gs, tmp_path, capsys):
        pdf = tmp_path / "in.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")
        code = main([str(pdf)])
        assert code == 1
        err = capsys.readouterr().err
        assert "Ghostscript is not installed" in err


class TestMissingInput:
    def test_missing_input_path_reports_error(self, mock_gs, tmp_path, capsys):
        code = main([str(tmp_path / "nope.pdf")])
        assert code == 1
        assert "does not exist" in capsys.readouterr().err


class TestSingleFileMode:
    def test_compress_single_file_with_output_flag(
        self, mock_gs, make_pdf, tmp_path, capsys
    ):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        code = main([str(input_path), "-o", str(output_path)])
        assert code == 0
        assert output_path.exists()
        out = capsys.readouterr().out
        assert "PDFXZ REPORT" in out
        assert "Successful         1" in out

    def test_compress_single_file_positional_output(self, mock_gs, make_pdf, tmp_path):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        code = main([str(input_path), str(output_path)])
        assert code == 0
        assert output_path.exists()

    def test_default_output_naming(self, mock_gs, make_pdf):
        input_path = make_pdf("report.pdf")
        code = main([str(input_path)])
        assert code == 0
        assert (input_path.parent / "report_compressed.pdf").exists()

    def test_non_pdf_input_rejected(self, mock_gs, tmp_path, capsys):
        txt = tmp_path / "notes.txt"
        txt.write_text("hi")
        code = main([str(txt)])
        assert code == 1
        assert "not a .pdf" in capsys.readouterr().err


class TestDirectoryMode:
    def test_compress_directory_top_level(self, mock_gs, make_pdf, tmp_path, capsys):
        make_pdf("a.pdf", directory=tmp_path / "papers")
        make_pdf("b.pdf", directory=tmp_path / "papers")
        make_pdf("nested.pdf", directory=tmp_path / "papers" / "sub")

        out_dir = tmp_path / "compressed"
        code = main([str(tmp_path / "papers"), "-o", str(out_dir), "--parents"])
        assert code == 0

        assert (out_dir / "a_compressed.pdf").exists()
        assert (out_dir / "b_compressed.pdf").exists()
        assert not (
            out_dir / "nested_compressed.pdf"
        ).exists()  # non-recursive by default

        out = capsys.readouterr().out
        assert "Discovered 2 PDF file(s)" in out

    def test_compress_directory_recursive_preserves_structure(
        self, mock_gs, make_pdf, tmp_path
    ):
        make_pdf("a.pdf", directory=tmp_path / "papers")
        make_pdf("report.pdf", directory=tmp_path / "papers" / "sub_a")
        make_pdf("report.pdf", directory=tmp_path / "papers" / "sub_b")

        out_dir = tmp_path / "compressed"
        code = main(
            [str(tmp_path / "papers"), "-o", str(out_dir), "--parents", "--recursive"]
        )
        assert code == 0

        assert (out_dir / "a_compressed.pdf").exists()
        assert (out_dir / "sub_a" / "report_compressed.pdf").exists()
        assert (out_dir / "sub_b" / "report_compressed.pdf").exists()

    def test_quality_flag_is_accepted(self, mock_gs, make_pdf, tmp_path):
        make_pdf("a.pdf", directory=tmp_path / "papers")
        out_dir = tmp_path / "compressed"
        code = main(
            [str(tmp_path / "papers"), "-o", str(out_dir), "-q", "strong", "-p"]
        )
        assert code == 0

    def test_empty_directory_reports_error(self, mock_gs, tmp_path, capsys):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        code = main([str(empty_dir)])
        assert code == 1
        assert "No PDF files found" in capsys.readouterr().err

    def test_batch_continues_after_one_failure(
        self, mock_gs, make_pdf, tmp_path, monkeypatch, capsys
    ):
        # One invalid ("skipped") file among valid ones must not abort the batch.
        make_pdf("good.pdf", directory=tmp_path / "papers")
        make_pdf("bad.pdf", content=b"not a pdf", directory=tmp_path / "papers")

        out_dir = tmp_path / "compressed"
        code = main([str(tmp_path / "papers"), "-o", str(out_dir), "--parents"])

        assert (out_dir / "good_compressed.pdf").exists()
        assert not (out_dir / "bad_compressed.pdf").exists()
        out = capsys.readouterr().out
        assert "Skipped (invalid)  1" in out
        assert (
            code == 1
        )  # nonzero because not everything succeeded, but batch still ran to completion
