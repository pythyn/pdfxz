"""Ghostscript-backed PDF compression engine.

`PDFCompressor` is the only module in pdfxz that knows Ghostscript exists.
It has no knowledge of the TUI, the CLI, or the scanner. Given an input
path, an output path, and a profile, it returns a structured
`CompressionResult` - never raises for ordinary failure modes (missing
Ghostscript, bad exit code, collisions), only for programmer errors.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

from .models import CompressionResult, CompressionStatus
from .profiles import CompressionProfile
from .utils import ensure_parent_dir, is_same_path, locate_ghostscript

logger = logging.getLogger("pdfxz.compressor")

# Sentinel distinguishing "not yet resolved" from a resolved-but-absent
# Ghostscript path. `None` can't serve this role because `locate_ghostscript`
# legitimately returns `None` when Ghostscript isn't found - that's a valid,
# cacheable resolution, not "unresolved". Declared before first use for
# readability; Python only needs it to exist by the time `gs_path` is called.
_UNSET = object()


class GhostscriptNotFoundError(RuntimeError):
    """Raised internally when a command needs Ghostscript and it's absent."""


class PDFCompressor:
    """Wraps a single Ghostscript invocation."""

    def __init__(self, gs_path: str | None = None):
        self._explicit_path = gs_path
        self._resolved_path: str | None | object = _UNSET

    @property
    def gs_path(self) -> str | None:
        """The resolved Ghostscript executable path, or None if not found.

        Resolved lazily and cached on first access rather than in
        `__init__`, so constructing a `PDFCompressor` never touches the
        filesystem/PATH before it's actually needed (e.g. in tests that
        only care about argument-building).
        """
        if self._resolved_path is _UNSET:
            self._resolved_path = locate_ghostscript(self._explicit_path)
        return self._resolved_path  # type: ignore[return-value]

    def is_available(self) -> bool:
        """Whether a usable Ghostscript executable was found."""
        return self.gs_path is not None

    def build_command(
        self, input_path: Path, output_path: Path, profile: CompressionProfile
    ) -> list[str]:
        """Build the Ghostscript argument list. Never uses shell=True / string concatenation."""
        if self.gs_path is None:
            raise GhostscriptNotFoundError(
                "Ghostscript is not installed.\n"
                "Install Ghostscript and ensure 'gs' (or 'gswin64c' on Windows) is available on PATH."
            )
        command = [self.gs_path]
        command.extend(profile.gs_args())
        command.append(f"-sOutputFile={output_path}")
        command.append(str(input_path))
        return command

    def compress(
        self,
        input_path: Path,
        output_path: Path,
        profile: CompressionProfile,
        *,
        overwrite: bool = False,
        create_parents: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> CompressionResult:
        """Compress a single file, returning a structured result.

        Safety guarantees:
          - refuses to run if input and output resolve to the same file
          - refuses to overwrite an existing output unless `overwrite=True`
          - deletes any partial output file on failure or cancellation
          - never modifies or deletes the input file
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if is_same_path(input_path, output_path):
            logger.error(
                "Refusing to compress: output path equals input path (%s)", input_path
            )
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                error="Output path is the same as the input path.",
            )

        if output_path.exists() and not overwrite:
            logger.warning(
                "Refusing to overwrite existing output without --overwrite: %s",
                output_path,
            )
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                error=f"Output file already exists: {output_path} (use --overwrite to replace it).",
            )

        try:
            ensure_parent_dir(output_path, create_parents)
        except OSError as exc:
            logger.error(
                "Could not prepare output directory for '%s': %s", output_path, exc
            )
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                error=str(exc),
            )

        try:
            original_size = input_path.stat().st_size
        except OSError as exc:
            logger.error("Failed to read file size for '%s': %s", input_path, exc)
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                error=f"Failed to read file size for '{input_path}': {exc}",
            )

        try:
            command = self.build_command(input_path, output_path, profile)
        except GhostscriptNotFoundError as exc:
            logger.error("Ghostscript not found; cannot compress '%s'", input_path)
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                original_size=original_size,
                error=str(exc),
            )

        logger.debug("Running: %s", " ".join(command))
        logger.info(
            "Compressing '%s' -> '%s' (profile: %s)",
            input_path,
            output_path,
            profile.key,
        )

        start = time.perf_counter()
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            logger.error("Failed to launch Ghostscript for '%s': %s", input_path, exc)
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                original_size=original_size,
                error=f"Failed to launch Ghostscript: {exc}",
            )

        cancelled = False
        stdout_text = ""
        stderr_text = ""
        # Poll with a short timeout so a cancel_event set from another thread
        # is noticed promptly, without spawning an extra watcher thread.
        # Retrying communicate() after TimeoutExpired is the documented
        # pattern for this in the subprocess docs.
        while True:
            try:
                stdout_text, stderr_text = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    process.terminate()
                    try:
                        stdout_text, stderr_text = process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout_text, stderr_text = process.communicate()
                    break
        elapsed = time.perf_counter() - start

        if cancelled:
            _cleanup_partial(output_path)
            logger.info("Compression cancelled by user: %s", input_path)
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.CANCELLED,
                original_size=original_size,
                elapsed_seconds=elapsed,
                error="Cancelled by user.",
            )

        if process.returncode != 0:
            _cleanup_partial(output_path)
            message = (stderr_text or stdout_text or "").strip() or (
                f"Ghostscript exited with code {process.returncode}."
            )
            logger.error(
                "Ghostscript failed for '%s' (exit code %s): %s",
                input_path,
                process.returncode,
                message,
            )
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                original_size=original_size,
                elapsed_seconds=elapsed,
                error=message,
            )

        if not output_path.exists():
            logger.error(
                "Ghostscript reported success but produced no output file: %s",
                output_path,
            )
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                original_size=original_size,
                elapsed_seconds=elapsed,
                error="Ghostscript reported success but produced no output file.",
            )

        try:
            compressed_size = output_path.stat().st_size
        except OSError as exc:
            logger.error(
                "Failed to read output file size for '%s': %s", output_path, exc
            )
            return CompressionResult(
                input_path=input_path,
                output_path=None,
                status=CompressionStatus.FAILED,
                original_size=original_size,
                elapsed_seconds=elapsed,
                error=f"Failed to read output file size: {exc}",
            )

        if compressed_size < original_size:
            status = CompressionStatus.SUCCESS
        elif compressed_size == original_size:
            status = CompressionStatus.UNCHANGED
        else:
            status = CompressionStatus.LARGER

        logger.info(
            "Compressed '%s': %d -> %d bytes (%s) in %.2fs",
            input_path,
            original_size,
            compressed_size,
            status.value,
            elapsed,
        )
        return CompressionResult(
            input_path=input_path,
            output_path=output_path,
            status=status,
            original_size=original_size,
            compressed_size=compressed_size,
            elapsed_seconds=elapsed,
        )


def _cleanup_partial(output_path: Path) -> None:
    """Remove a partially-written output file after failure/cancellation.

    Never touches the input file.
    """
    try:
        if output_path.exists():
            output_path.unlink()
    except OSError:
        logger.warning("Failed to remove partial output file: %s", output_path)
