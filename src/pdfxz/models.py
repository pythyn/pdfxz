"""Typed data models shared across pdfxz.

Kept dependency-free (no Textual, no subprocess) so they can be imported
by every layer - scanner, compressor, CLI, and TUI - without pulling in
unrelated machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CompressionStatus(str, Enum):
    """Outcome of attempting to compress a single file."""

    SUCCESS = "success"  # compressed output is smaller than the input
    UNCHANGED = "unchanged"  # compressed output is the same size as the input
    LARGER = "larger"  # compressed output is larger than the input
    FAILED = "failed"  # Ghostscript failed, or another error occurred
    SKIPPED = "skipped"  # input failed validation; Ghostscript was never invoked
    CANCELLED = (
        "cancelled"  # the user cancelled the batch while this item was pending/running
    )

    @property
    def is_completed(self) -> bool:
        """True if Ghostscript actually ran and produced output."""
        return self in (
            CompressionStatus.SUCCESS,
            CompressionStatus.UNCHANGED,
            CompressionStatus.LARGER,
        )


class AppPhase(str, Enum):
    """Explicit lifecycle state for the interactive application.

    Not currently consumed anywhere: the TUI encodes state implicitly via
    which `Screen` is active (see `app.py`) rather than an explicit phase
    variable. Kept as part of the public model surface for callers who may
    want an explicit phase enum (e.g. a future non-Textual front end);
    left in place rather than removed so this refactor stays behavior- and
    API-preserving.
    """

    CONFIGURING = "configuring"
    SCANNING = "scanning"
    READY = "ready"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class CompressionResult:
    """Structured outcome for a single input file."""

    input_path: Path
    output_path: Path | None
    status: CompressionStatus
    original_size: int = 0
    compressed_size: int | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether this item should count as a processed (non-failed) result."""
        return self.status.is_completed

    @property
    def saved_bytes(self) -> int:
        if self.compressed_size is None:
            return 0
        return self.original_size - self.compressed_size

    @property
    def reduction_percent(self) -> float:
        if not self.original_size or self.compressed_size is None:
            return 0.0
        return (self.saved_bytes / self.original_size) * 100

    @property
    def ratio(self) -> float | None:
        if not self.compressed_size:
            return None
        return self.original_size / self.compressed_size


@dataclass(slots=True)
class BatchResult:
    """Aggregate outcome for a batch of input files."""

    results: list[CompressionResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    cancelled: bool = False

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def successful(self) -> int:
        return sum(1 for result in self.results if result.status.is_completed)

    @property
    def failed(self) -> int:
        return sum(
            1 for result in self.results if result.status == CompressionStatus.FAILED
        )

    @property
    def skipped(self) -> int:
        return sum(
            1 for result in self.results if result.status == CompressionStatus.SKIPPED
        )

    @property
    def cancelled_count(self) -> int:
        return sum(
            1 for result in self.results if result.status == CompressionStatus.CANCELLED
        )

    @property
    def original_size(self) -> int:
        return sum(
            result.original_size for result in self.results if result.original_size
        )

    @property
    def compressed_size(self) -> int:
        return sum(
            result.compressed_size for result in self.results if result.compressed_size
        )

    @property
    def saved_bytes(self) -> int:
        return self.original_size - self.compressed_size

    @property
    def reduction_percent(self) -> float:
        if not self.original_size:
            return 0.0
        return (self.saved_bytes / self.original_size) * 100

    @property
    def largest_saving(self) -> CompressionResult | None:
        completed_results = [
            result for result in self.results if result.compressed_size is not None
        ]
        if not completed_results:
            return None
        return max(completed_results, key=lambda result: result.saved_bytes)
