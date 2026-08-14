"""Pure formatting and calculation helpers.

Deliberately dependency-free and side-effect-free so they are trivial to
unit test. No Path, subprocess, or Textual imports belong in this module.
"""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_bytes(num_bytes: int) -> str:
    """Render a byte count as a human-readable size (e.g. ``78.30 MB``)."""
    if num_bytes < 0:
        return f"-{format_bytes(-num_bytes)}"

    size = float(num_bytes)
    for unit in _UNITS:
        if unit == "B":
            if size < 1024:
                return f"{int(size)} B"
        elif size < 1024 or unit == _UNITS[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} {_UNITS[-1]}"  # pragma: no cover - unreachable in practice


def format_duration(seconds: float) -> str:
    """Render a duration as ``MM:SS`` (or ``HH:MM:SS`` for long batches)."""
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def reduction_percent(original: int, compressed: int) -> float:
    """Percentage size reduction. Negative if the output grew. 0 if original is 0."""
    if original <= 0:
        return 0.0
    return ((original - compressed) / original) * 100


def compression_ratio(original: int, compressed: int) -> float | None:
    """Compression ratio as original:compressed, or None if compressed is 0."""
    if compressed <= 0:
        return None
    return original / compressed


def format_ratio(ratio: float | None) -> str:
    """Render a compression ratio as ``N.NN:1``, or ``n/a`` when undefined."""
    if ratio is None:
        return "n/a"
    return f"{ratio:.2f}:1"


def format_mb(num_bytes: int, decimals: int = 2) -> str:
    """Render a byte count in megabytes only, e.g. ``78.30 MB``.

    Unlike `format_bytes`, this never switches units (B/KB/GB/...). The TUI
    uses this exclusively so file sizes stay visually consistent and easy
    to scan down a column; the CLI keeps `format_bytes` for its report,
    where auto-scaling units suit a plain-text summary better.
    """
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.{decimals}f} MB"


def truncate_filename(name: str, max_length: int = 28) -> str:
    """Shorten a filename to at most `max_length` characters, e.g.
    ``very_long_filename_from_a_scanner.pdf`` -> ``very_long_filename_from_a...``.

    Used anywhere a filename is displayed in a fixed-width UI element so a
    single long name can't stretch the layout. The full name should still
    be surfaced elsewhere (e.g. a tooltip) wherever the UI framework
    supports it.
    """
    if len(name) <= max_length:
        return name
    if max_length <= 1:
        return name[:max_length]
    return name[: max_length - 1] + "…"


def format_size_change(original: int, compressed: int) -> str:
    """Human-readable size delta, e.g. ``-78.30 MB (-68.16%)`` or ``+4.22 MB (+12.51%)``."""
    size_delta = original - compressed
    reduction_pct = reduction_percent(original, compressed)
    if size_delta > 0:
        return f"-{format_bytes(size_delta)} (-{reduction_pct:.2f}%)"
    if size_delta < 0:
        return f"+{format_bytes(-size_delta)} (+{-reduction_pct:.2f}%)"
    return "0 B (0.00%)"
