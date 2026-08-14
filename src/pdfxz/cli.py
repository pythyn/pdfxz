"""Command-line interface.

Running `pdfxz` with no INPUT launches the interactive TUI. Supplying
INPUT (and optionally OUTPUT) runs entirely non-interactively, which is
what shell scripts and automation should use. `--no-tui` guards against a
script accidentally dropping into the interactive TUI (e.g. a missing
argument in CI) by failing fast instead of blocking on a terminal that
may not exist.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from . import __version__
from .compressor import PDFCompressor
from .formatting import format_bytes, format_duration, format_size_change
from .models import BatchResult, CompressionResult, CompressionStatus
from .profiles import DEFAULT_QUALITY, QUALITY_PROFILES, get_profile
from .scanner import discover_pdfs
from .utils import configure_logging, plan_batch_outputs, plan_single_output
from .workers import BatchJob, BatchRunner

logger = logging.getLogger("pdfxz.cli")

# NOTE ON print() vs logging: every print() in this module is part of the
# CLI's actual output contract (the report/progress/error text a user or a
# calling script reads), not an informal debug trace - it's asserted on
# directly by the CLI test suite (see tests/test_cli.py) and documented in
# the README. Routing it through `logging` instead would change real
# behaviour (WARNING is the default level, so most of this text would
# simply stop appearing) rather than just its formatting, so it stays as
# print(). `logger` above is reserved for genuine diagnostics that should
# be invisible unless --debug is passed.


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI's argument parser.

    Kept separate from `main()` so tests (and anything embedding pdfxz)
    can inspect/exercise the parser without going through `parse_args`.
    """
    parser = argparse.ArgumentParser(
        prog="pdfxz",
        description="Compress PDF files with Ghostscript, interactively or from the command line.",
        epilog=(
            "Examples:\n"
            "  pdfxz                                   launch the interactive TUI\n"
            "  pdfxz paper.pdf                          compress to paper_compressed.pdf\n"
            "  pdfxz input.pdf output.pdf                compress to a specific file\n"
            "  pdfxz input.pdf -o output.pdf             same, using -o\n"
            "  pdfxz ~/papers -o ~/compressed            compress a whole directory\n"
            "  pdfxz ~/papers -o ~/compressed -q strong -r\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        metavar="INPUT",
        help="A PDF file or a directory containing PDFs.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        metavar="OUTPUT",
        help="Output PDF file or directory (positional form).",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_opt",
        type=Path,
        metavar="PATH",
        help="Output PDF file or directory.",
    )
    parser.add_argument(
        "-p",
        "--parents",
        action="store_true",
        help="Create missing output directories (like 'mkdir -p').",
    )
    parser.add_argument(
        "-q",
        "--quality",
        choices=sorted(QUALITY_PROFILES),
        default=DEFAULT_QUALITY,
        metavar="LEVEL",
        help="Compression profile: "
        + ", ".join(sorted(QUALITY_PROFILES))
        + f" (default: {DEFAULT_QUALITY}).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories when INPUT is a directory (default: off, top level only).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting an existing output file.",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Never launch the interactive TUI; exit with an error if INPUT is missing instead of prompting.",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable verbose debug logging."
    )
    parser.add_argument("--version", action="version", version=f"pdfxz {__version__}")
    return parser


def _resolve_output_arg(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> Path | None:
    """Reconcile the positional OUTPUT and -o/--output forms.

    Both exist for ergonomics (`pdfxz in.pdf out.pdf` and
    `pdfxz in.pdf -o out.pdf` are both natural to type), but supplying
    both at once is ambiguous, so that's rejected via `parser.error`
    (argparse's standard way to report a usage error - prints usage and
    exits with status 2) rather than silently preferring one.
    """
    if args.output_opt is not None and args.output is not None:
        parser.error(
            "specify OUTPUT either positionally or with -o/--output, not both."
        )
    return args.output_opt if args.output_opt is not None else args.output


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `pdfxz` command (see `pyproject.toml`'s `[project.scripts]`)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.debug)
    logger.debug("Parsed CLI arguments: %s", vars(args))

    output_arg = _resolve_output_arg(args, parser)

    if args.input is None:
        if args.no_tui:
            parser.error("INPUT is required when --no-tui is set.")
        return _launch_tui()

    return _run_cli(args.input, output_arg, args)


def _launch_tui() -> int:
    try:
        from .app import PDFXZApp
    except ImportError as exc:  # pragma: no cover - textual is a hard dependency
        print(f"Failed to start the interactive interface: {exc}", file=sys.stderr)
        return 1
    PDFXZApp().run()
    return 0


def _run_cli(
    input_path: Path, output_arg: Path | None, args: argparse.Namespace
) -> int:
    input_path = input_path.expanduser()
    profile = get_profile(args.quality)
    compressor = PDFCompressor()

    if not compressor.is_available():
        print(
            "Ghostscript is not installed.\n"
            "Install Ghostscript and ensure 'gs' (or 'gswin64c' on Windows) is available on PATH.",
            file=sys.stderr,
        )
        return 1

    if not input_path.exists():
        print(f"Input path does not exist: {input_path}", file=sys.stderr)
        return 1

    output_arg = output_arg.expanduser() if output_arg else None
    runner = BatchRunner(compressor)

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            print(f"Input file is not a .pdf: {input_path}", file=sys.stderr)
            return 1
        output_path = plan_single_output(input_path, output_arg)
        jobs = [BatchJob(input_path=input_path, output_path=output_path)]
    else:
        discovered = discover_pdfs(input_path, recursive=args.recursive)
        if not discovered:
            scope = "recursively" if args.recursive else "at the top level"
            print(f"No PDF files found {scope} in: {input_path}", file=sys.stderr)
            return 1
        output_root = output_arg or (
            input_path.parent / f"{input_path.name}_compressed"
        )
        mapping = plan_batch_outputs(discovered, input_path, output_root)
        jobs = [
            BatchJob(input_path=src_path, output_path=dst_path)
            for src_path, dst_path in mapping.items()
        ]
        print(f"Discovered {len(jobs)} PDF file(s) in {input_path}")

    cancel_event = threading.Event()

    def on_progress(result: CompressionResult, index: int, total: int) -> None:
        _print_result_line(result, index, total)

    try:
        batch = runner.run(
            jobs,
            profile,
            overwrite=args.overwrite,
            create_parents=args.parents,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
    except KeyboardInterrupt:
        cancel_event.set()
        print("\nCancelling... (Ctrl+C again to force-quit)", file=sys.stderr)
        return 130

    _print_summary(batch)
    return (
        0
        if (batch.failed == 0 and batch.skipped == 0 and batch.cancelled_count == 0)
        else 1
    )


def _print_result_line(result: CompressionResult, index: int, total: int) -> None:
    prefix = f"[{index}/{total}]"
    name = result.input_path.name
    if result.status == CompressionStatus.SKIPPED:
        print(f"{prefix} SKIP    {name}: {result.error}")
    elif result.status == CompressionStatus.FAILED:
        print(f"{prefix} FAIL    {name}: {result.error}")
    elif result.status == CompressionStatus.CANCELLED:
        print(f"{prefix} CANCEL  {name}")
    else:
        change = format_size_change(
            result.original_size, result.compressed_size or result.original_size
        )
        before = format_bytes(result.original_size)
        after = format_bytes(result.compressed_size or 0)
        print(f"{prefix} OK      {name}: {before} -> {after} ({change})")


def _print_summary(batch: BatchResult) -> None:
    print()
    print("=" * 60)
    print("PDFXZ REPORT")
    print("=" * 60)
    print(f"Files discovered   {batch.total}")
    print(f"Successful         {batch.successful}")
    print(f"Failed             {batch.failed}")
    if batch.skipped:
        print(f"Skipped (invalid)  {batch.skipped}")
    if batch.cancelled_count:
        print(f"Cancelled          {batch.cancelled_count}")
    print()
    print(f"Original size      {format_bytes(batch.original_size)}")
    print(f"Compressed size    {format_bytes(batch.compressed_size)}")
    print(f"Total saved        {format_bytes(batch.saved_bytes)}")
    print(f"Reduction          {batch.reduction_percent:.2f}%")
    print(f"Elapsed time       {format_duration(batch.elapsed_seconds)}")
    largest = batch.largest_saving
    if largest and largest.saved_bytes > 0:
        print()
        print(
            f"Largest saving: {largest.input_path.name}  -{format_bytes(largest.saved_bytes)}"
        )
    print("=" * 60)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
