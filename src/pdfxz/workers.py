"""Batch orchestration.

`BatchRunner` sits between the scanner/compressor and any UI. It has no
Textual imports and no `print()` calls - the CLI drives it synchronously
in the main thread, and the TUI drives it inside a Textual worker thread,
but both call exactly the same code, satisfying the requirement that CLI
and TUI share one core implementation.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .compressor import PDFCompressor
from .models import BatchResult, CompressionResult, CompressionStatus
from .profiles import CompressionProfile
from .scanner import validate_pdf

logger = logging.getLogger("pdfxz.workers")

ProgressCallback = Callable[[CompressionResult, int, int], None]


@dataclass(slots=True)
class BatchJob:
    """A single planned (input, output) pair awaiting compression."""

    input_path: Path
    output_path: Path


class BatchRunner:
    """Runs a sequence of `BatchJob`s through validation and compression.

    Processes jobs one at a time (see module docstring in `compressor.py`
    for the rationale: predictable resource usage over unrestricted
    parallel Ghostscript processes). One failed file never aborts the
    batch - the loop always continues to the next job.
    """

    def __init__(self, compressor: PDFCompressor | None = None):
        self.compressor = compressor or PDFCompressor()

    def run(
        self,
        jobs: Iterable[BatchJob],
        profile: CompressionProfile,
        *,
        overwrite: bool = False,
        create_parents: bool = False,
        on_progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> BatchResult:
        jobs = list(jobs)
        total = len(jobs)
        results: list[CompressionResult] = []
        start = time.perf_counter()
        logger.info("Starting batch: %d file(s), profile '%s'", total, profile.key)

        for index, job in enumerate(jobs, start=1):
            if cancel_event is not None and cancel_event.is_set():
                result = CompressionResult(
                    input_path=job.input_path,
                    output_path=None,
                    status=CompressionStatus.CANCELLED,
                    error="Cancelled by user.",
                )
            else:
                validation = validate_pdf(job.input_path)
                if not validation.ok:
                    result = CompressionResult(
                        input_path=job.input_path,
                        output_path=None,
                        status=CompressionStatus.SKIPPED,
                        error=validation.reason,
                    )
                else:
                    result = self.compressor.compress(
                        job.input_path,
                        job.output_path,
                        profile,
                        overwrite=overwrite,
                        create_parents=create_parents,
                        cancel_event=cancel_event,
                    )

            results.append(result)
            if on_progress:
                on_progress(result, index, total)

        elapsed = time.perf_counter() - start
        cancelled = any(
            result.status == CompressionStatus.CANCELLED for result in results
        )
        logger.info(
            "Batch finished in %.2fs: %d file(s) processed, cancelled=%s",
            elapsed,
            total,
            cancelled,
        )
        return BatchResult(
            results=results, elapsed_seconds=elapsed, cancelled=cancelled
        )
