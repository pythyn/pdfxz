from __future__ import annotations

import threading
import time

from pdfxz.compressor import PDFCompressor
from pdfxz.models import CompressionStatus
from pdfxz.profiles import QUALITY_PROFILES

BALANCED = QUALITY_PROFILES["balanced"]


class TestAvailability:
    def test_available_when_gs_found(self, mock_gs):
        assert PDFCompressor().is_available() is True

    def test_unavailable_when_gs_missing(self, no_gs):
        assert PDFCompressor().is_available() is False


class TestGhostscriptMissing:
    def test_compress_reports_clear_error(self, no_gs, make_pdf, tmp_path):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        result = PDFCompressor().compress(input_path, output_path, BALANCED)
        assert result.status == CompressionStatus.FAILED
        assert "Ghostscript is not installed" in result.error
        assert not output_path.exists()


class TestSuccessfulCompression:
    def test_success_status_and_sizes(self, mock_gs, make_pdf, tmp_path):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        result = PDFCompressor().compress(input_path, output_path, BALANCED)

        assert result.status == CompressionStatus.SUCCESS
        assert result.output_path == output_path
        assert result.original_size == input_path.stat().st_size
        assert result.compressed_size == output_path.stat().st_size
        assert result.compressed_size < result.original_size
        assert result.saved_bytes > 0
        assert result.elapsed_seconds >= 0
        assert output_path.exists()
        # input must never be touched
        assert input_path.exists()

    def test_command_uses_argument_list_not_shell_string(
        self, mock_gs, make_pdf, tmp_path
    ):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        command = PDFCompressor().build_command(input_path, output_path, BALANCED)
        assert isinstance(command, list)
        assert all(isinstance(part, str) for part in command)
        assert str(input_path) in command
        assert f"-sOutputFile={output_path}" in command


class TestUnchangedAndLarger:
    def test_unchanged_status(self, mock_gs, make_pdf, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_GS_MODE", "unchanged")
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        result = PDFCompressor().compress(input_path, output_path, BALANCED)
        assert result.status == CompressionStatus.UNCHANGED
        assert result.saved_bytes == 0
        assert result.reduction_percent == 0.0

    def test_larger_status(self, mock_gs, make_pdf, tmp_path, monkeypatch):
        monkeypatch.setenv("FAKE_GS_MODE", "larger")
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        result = PDFCompressor().compress(input_path, output_path, BALANCED)
        assert result.status == CompressionStatus.LARGER
        assert result.saved_bytes < 0


class TestFailureCleanup:
    def test_nonzero_exit_cleans_up_and_reports_failure(
        self, mock_gs, make_pdf, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FAKE_GS_MODE", "fail")
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        result = PDFCompressor().compress(input_path, output_path, BALANCED)
        assert result.status == CompressionStatus.FAILED
        assert "simulated failure" in result.error
        assert not output_path.exists()
        assert input_path.exists()  # input untouched

    def test_missing_output_despite_zero_exit_is_reported(
        self, mock_gs, make_pdf, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FAKE_GS_MODE", "no_output")
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        result = PDFCompressor().compress(input_path, output_path, BALANCED)
        assert result.status == CompressionStatus.FAILED
        assert "no output file" in result.error.lower()


class TestCollisionProtection:
    def test_same_input_and_output_path_rejected(self, mock_gs, make_pdf):
        input_path = make_pdf("in.pdf")
        result = PDFCompressor().compress(input_path, input_path, BALANCED)
        assert result.status == CompressionStatus.FAILED
        assert "same as the input" in result.error

    def test_existing_output_rejected_without_overwrite(
        self, mock_gs, make_pdf, tmp_path
    ):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        output_path.write_bytes(b"already here")
        result = PDFCompressor().compress(
            input_path, output_path, BALANCED, overwrite=False
        )
        assert result.status == CompressionStatus.FAILED
        assert "already exists" in result.error
        # original "existing output" content must be left alone
        assert output_path.read_bytes() == b"already here"

    def test_existing_output_allowed_with_overwrite(self, mock_gs, make_pdf, tmp_path):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        output_path.write_bytes(b"already here")
        result = PDFCompressor().compress(
            input_path, output_path, BALANCED, overwrite=True
        )
        assert result.status == CompressionStatus.SUCCESS
        assert output_path.read_bytes() != b"already here"


class TestOutputDirectoryCreation:
    def test_missing_parent_dir_fails_without_parents_flag(
        self, mock_gs, make_pdf, tmp_path
    ):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "does" / "not" / "exist" / "out.pdf"
        result = PDFCompressor().compress(
            input_path, output_path, BALANCED, create_parents=False
        )
        assert result.status == CompressionStatus.FAILED
        assert "does not exist" in result.error

    def test_missing_parent_dir_created_with_parents_flag(
        self, mock_gs, make_pdf, tmp_path
    ):
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "does" / "not" / "exist" / "out.pdf"
        result = PDFCompressor().compress(
            input_path, output_path, BALANCED, create_parents=True
        )
        assert result.status == CompressionStatus.SUCCESS
        assert output_path.exists()


class TestCancellation:
    def test_cancel_mid_run_marks_cancelled_and_cleans_up(
        self, mock_gs, make_pdf, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("FAKE_GS_MODE", "slow")
        monkeypatch.setenv("FAKE_GS_SLEEP", "3")
        input_path = make_pdf("in.pdf")
        output_path = tmp_path / "out.pdf"
        cancel_event = threading.Event()

        def cancel_soon():
            time.sleep(0.3)
            cancel_event.set()

        threading.Thread(target=cancel_soon, daemon=True).start()

        start = time.perf_counter()
        result = PDFCompressor().compress(
            input_path, output_path, BALANCED, cancel_event=cancel_event
        )
        elapsed = time.perf_counter() - start

        assert result.status == CompressionStatus.CANCELLED
        assert not output_path.exists()
        assert input_path.exists()
        # Should return promptly after cancellation, not wait out the full sleep.
        assert elapsed < 3.0
