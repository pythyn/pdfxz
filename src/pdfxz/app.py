"""The interactive Textual TUI.

Three screens, pushed in sequence: `ConfigScreen` (input/output/quality)
-> `ProcessingScreen` (live progress, cancellable) -> `ReportScreen`
(summary + per-file table), plus a `DirectoryPicker` modal used by both
the input and output fields on `ConfigScreen`. The TUI is a thin
consumer of `BatchRunner` and `PDFCompressor` - all business logic lives
in `workers.py` and `compressor.py`, so the CLI and the TUI never
duplicate it.

The TUI intentionally exposes fewer knobs than the CLI (no
recursive/overwrite/create-directory toggles): directories are always
scanned recursively, missing output directories are always created, and
an existing output is never overwritten - a fresh, uniquely-named file
is written alongside it instead (see `utils.unique_output_path`). The
CLI is unaffected and keeps its explicit flags for scripting.

Ghostscript runs inside a Textual thread worker (`@work(thread=True)`),
never on the UI event loop, so the interface stays responsive and a
determinate progress bar can be driven by real per-file completion
events rather than fabricated intra-file percentages.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Static,
)
from textual.widgets.data_table import RowKey

from .compressor import PDFCompressor
from .formatting import (
    format_duration,
    format_mb,
    format_size_change,
    truncate_filename,
)
from .models import BatchResult, CompressionResult, CompressionStatus
from .profiles import DEFAULT_QUALITY, QUALITY_PROFILES, get_profile
from .scanner import discover_pdfs
from .utils import plan_batch_outputs, plan_single_output, unique_output_path
from .workers import BatchJob, BatchRunner

logger = logging.getLogger("pdfxz.app")

# NOTE ON LOGGING SCOPE: per-file and per-batch compression events are
# already logged by `compressor.py`/`workers.py`, which the TUI calls into
# via the same `BatchRunner`/`PDFCompressor` used by the CLI - duplicating
# those log lines here would just be noise. The handful of `logger` calls
# in this module cover events the TUI alone knows about (e.g. the user
# pressing Cancel, or Ghostscript being unavailable before a batch even
# starts), not compression outcomes themselves.

_STATUS_LABELS = {
    CompressionStatus.SUCCESS: "OK",
    CompressionStatus.UNCHANGED: "UNCHANGED",
    CompressionStatus.LARGER: "LARGER",
    CompressionStatus.FAILED: "FAILED",
    CompressionStatus.SKIPPED: "SKIPPED",
    CompressionStatus.CANCELLED: "CANCELLED",
}

_FILENAME_COLUMN_WIDTH = 30

# Letter-spaced wordmark. Terminal cells can't be individually scaled up
# the way a GUI font can, so "noticeably larger" is achieved through
# spacing + weight + a background band (see app.tcss) rather than
# unusual Unicode glyph forms, which render inconsistently (or as tofu
# boxes) across terminal fonts.
_TITLE_TEXT = "P D F X Z"


class QualitySlider(Static, can_focus=True):
    """A compact, volume-control-style widget for picking a compression profile.

    Backed by the same five `QUALITY_PROFILES` keys used by the CLI's
    `-q/--quality` flag - only the presentation differs.
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("left", "decrease", "Less compression"),
        ("right", "increase", "More compression"),
    ]

    KEYS: ClassVar[list[str]] = list(QUALITY_PROFILES.keys())

    index: reactive[int] = reactive(0)

    class Changed(Message):
        """Posted whenever the selected profile changes."""

        def __init__(self, key: str) -> None:
            self.key = key
            super().__init__()

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.index = self.KEYS.index(DEFAULT_QUALITY)

    @property
    def value(self) -> str:
        return self.KEYS[self.index]

    def on_mount(self) -> None:
        self._render_text()

    def watch_index(self) -> None:
        self._render_text()

    def _render_text(self) -> None:
        profile = QUALITY_PROFILES[self.value]
        blocks = "".join(
            "\u25ae" if i <= self.index else "\u25af" for i in range(len(self.KEYS))
        )
        self.update(f"{blocks}  {profile.label}")

    def action_decrease(self) -> None:
        self._set_index(self.index - 1)

    def action_increase(self) -> None:
        self._set_index(self.index + 1)

    def _set_index(self, new_index: int) -> None:
        new_index = max(0, min(len(self.KEYS) - 1, new_index))
        if new_index != self.index:
            self.index = new_index
            self.post_message(self.Changed(self.value))

    def on_click(self, event) -> None:
        self.focus()
        midpoint = self.size.width / 2
        if event.x < midpoint:
            self.action_decrease()
        else:
            self.action_increase()


class DirectoryPicker(ModalScreen[Path | None]):
    """A file/folder browser built on Textual's built-in `DirectoryTree`.

    `select_files=True` lets the user pick a `.pdf` file or a folder
    (used for INPUT). `select_files=False` restricts picking to folders
    only (used for OUTPUT, which is always a destination directory - see
    the module docstring for why filenames are handled automatically).
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("escape", "cancel", "Cancel"),
        ("u", "use_folder", "Use this folder"),
    ]

    def __init__(self, start_path: Path, select_files: bool = True) -> None:
        super().__init__()
        self.start_path = start_path if start_path.is_dir() else start_path.parent
        self.select_files = select_files

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-body"):
            title = (
                "Select a PDF file or folder"
                if self.select_files
                else "Select a destination folder"
            )
            yield Static(title, id="picker-title")
            yield DirectoryTree(str(self.start_path), id="picker-tree")
            hint = (
                "enter: choose    u: use folder    esc: cancel"
                if self.select_files
                else "enter: open folder    u: use folder    esc: cancel"
            )
            yield Static(hint, id="picker-hint")
            with Horizontal(id="picker-actions"):
                yield Button("Use this folder", id="use-folder-button")
                yield Button("Cancel", id="picker-cancel-button")

    def on_mount(self) -> None:
        self.query_one(DirectoryTree).focus()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        path = Path(event.path)
        if self.select_files and path.suffix.lower() == ".pdf":
            self.dismiss(path)
        # Non-PDF files are simply not selectable inputs; ignore the event
        # rather than surfacing an error inside a modal.

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "use-folder-button":
            self.action_use_folder()
        elif event.button.id == "picker-cancel-button":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_use_folder(self) -> None:
        tree = self.query_one(DirectoryTree)
        node = tree.cursor_node
        if node is None or node.data is None:
            self.dismiss(self.start_path)
            return
        path = Path(node.data.path)
        if path.is_file():
            path = path.parent
        self.dismiss(path)


class ConfigScreen(Screen):
    """Screen 1: input, output, and compression settings."""

    # Textual's App already binds ctrl+q (to its own quit action, hidden
    # from the footer) and ctrl+c (to help_quit) with priority=True, so
    # neither key ever reaches a Screen-level binding of the same name -
    # "q" is used here instead so the shortcut is both functional and
    # visible in the footer.
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="config-body"):
            yield Static(_TITLE_TEXT, id="title")
            yield Static("PDF Compression Utility", id="subtitle")

            yield Static("INPUT", classes="field-label")
            with Horizontal(classes="field-row"):
                yield Input(placeholder="PDF file or folder…", id="input-field")
                yield Button(
                    "Browse…", id="browse-input-button", classes="browse-button"
                )

            yield Static("OUTPUT", classes="field-label")
            with Horizontal(classes="field-row"):
                yield Input(
                    placeholder="Destination folder (optional)…", id="output-field"
                )
                yield Button(
                    "Browse…", id="browse-output-button", classes="browse-button"
                )

            yield Static("QUALITY", classes="field-label")
            yield QualitySlider(id="quality-slider")

            yield Static("", id="validation-message")
            yield Button(
                "Compress PDFs", id="compress-button", variant="primary", disabled=True
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#input-field", Input).focus()
        if not PDFCompressor().is_available():
            logger.warning(
                "Ghostscript not found on PATH; compression is disabled until it's installed."
            )
            self.query_one("#validation-message", Static).update(
                "[red]Ghostscript was not found on PATH. Install it before compressing.[/red]"
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self._validate()

    def _validate(self) -> bool:
        input_text = self.query_one("#input-field", Input).value.strip()
        message = self.query_one("#validation-message", Static)
        button = self.query_one("#compress-button", Button)

        if not PDFCompressor().is_available():
            button.disabled = True
            return False

        if not input_text:
            message.update("")
            button.disabled = True
            return False

        path = Path(input_text).expanduser()
        if not path.exists():
            message.update(f"[red]Input does not exist: {path}[/red]")
            button.disabled = True
            return False
        if path.is_file() and path.suffix.lower() != ".pdf":
            message.update("[red]Input file must be a .pdf[/red]")
            button.disabled = True
            return False

        message.update("")
        button.disabled = False
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "compress-button":
            self._start_compression()
        elif event.button.id == "browse-input-button":
            self._browse_input()
        elif event.button.id == "browse-output-button":
            self._browse_output()

    def _browse_input(self) -> None:
        current = self.query_one("#input-field", Input).value.strip()
        start = Path(current).expanduser() if current else Path.home()
        if not start.exists():
            start = Path.home()
        self.app.push_screen(
            DirectoryPicker(start, select_files=True), self._on_input_picked
        )

    def _on_input_picked(self, path: Path | None) -> None:
        if path is None:
            return
        self.query_one("#input-field", Input).value = str(path)
        self._validate()

    def _browse_output(self) -> None:
        current = self.query_one("#output-field", Input).value.strip()
        start = Path(current).expanduser() if current else Path.home()
        if not start.exists():
            start = Path.home()
        self.app.push_screen(
            DirectoryPicker(start, select_files=False), self._on_output_picked
        )

    def _on_output_picked(self, path: Path | None) -> None:
        if path is None:
            return
        self.query_one("#output-field", Input).value = str(path)

    def _start_compression(self) -> None:
        if not self._validate():
            return

        input_text = self.query_one("#input-field", Input).value.strip()
        output_text = self.query_one("#output-field", Input).value.strip()
        quality = self.query_one("#quality-slider", QualitySlider).value

        input_path = Path(input_text).expanduser()
        output_path = Path(output_text).expanduser() if output_text else None
        message = self.query_one("#validation-message", Static)

        # Directories are always scanned recursively and missing output
        # directories are always created - see the module docstring for
        # why the TUI drops those toggles in favour of these defaults.
        if input_path.is_file():
            target = plan_single_output(input_path, output_path)
            jobs = [
                BatchJob(input_path=input_path, output_path=unique_output_path(target))
            ]
        else:
            discovered = discover_pdfs(input_path, recursive=True)
            if not discovered:
                message.update("[red]No PDF files found in that folder.[/red]")
                return
            output_root = output_path or (
                input_path.parent / f"{input_path.name}_compressed"
            )
            mapping = plan_batch_outputs(discovered, input_path, output_root)
            jobs = [
                BatchJob(input_path=src_path, output_path=unique_output_path(dst_path))
                for src_path, dst_path in mapping.items()
            ]

        self.app.push_screen(ProcessingScreen(jobs=jobs, quality=quality))

    def action_quit_app(self) -> None:
        self.app.exit()


class ProcessingScreen(Screen):
    """Screen 2: live progress for a running batch. Cancellable."""

    # Note: ctrl+c is NOT bound here - Textual's App intercepts it first
    # (priority binding to help_quit), so a Screen-level ctrl+c binding
    # would never fire. Escape is the one real, working shortcut, which
    # is why it's the only one advertised (button label, footer, docs).
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [("escape", "cancel", "Cancel")]

    def __init__(self, jobs: list[BatchJob], quality: str) -> None:
        super().__init__()
        self.jobs = jobs
        self.quality = quality
        self.cancel_event = threading.Event()
        self._successful = 0
        self._failed = 0
        self._start_time = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="processing-body"):
            yield Static("Compressing PDFs", id="processing-title")
            yield Static("-", id="current-file")
            yield Static(f"0 / {len(self.jobs)} files", id="files-counter")
            yield Static("0 succeeded  ·  0 failed", id="result-counters")
            yield Static("", id="current-result")
            yield Static("Elapsed 00:00", id="elapsed-counter")
            yield Button("Cancel (Esc)", id="cancel-button", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._start_time = time.perf_counter()
        self.set_interval(1.0, self._tick_elapsed)
        self.run_compression()

    def _tick_elapsed(self) -> None:
        elapsed = time.perf_counter() - self._start_time
        self.query_one("#elapsed-counter", Static).update(
            f"Elapsed {format_duration(elapsed)}"
        )

    @work(thread=True, exclusive=True)
    def run_compression(self) -> None:
        compressor = PDFCompressor()
        runner = BatchRunner(compressor)
        profile = get_profile(self.quality)

        def on_progress(result: CompressionResult, index: int, total: int) -> None:
            self.app.call_from_thread(self._update_progress, result, index, total)

        batch = runner.run(
            self.jobs,
            profile,
            # Output paths are pre-uniquified by ConfigScreen, and missing
            # parent directories are always created - see module docstring.
            overwrite=False,
            create_parents=True,
            on_progress=on_progress,
            cancel_event=self.cancel_event,
        )
        self.app.call_from_thread(self._finish, batch)

    def _update_progress(
        self, result: CompressionResult, index: int, total: int
    ) -> None:
        if result.status == CompressionStatus.CANCELLED:
            pass
        elif result.status.is_completed:
            self._successful += 1
        else:
            self._failed += 1

        file_widget = self.query_one("#current-file", Static)
        display_name = truncate_filename(result.input_path.name, _FILENAME_COLUMN_WIDTH)
        file_widget.update(display_name)
        file_widget.tooltip = str(result.input_path)

        self.query_one("#files-counter", Static).update(f"{index} / {total} files")
        self.query_one("#result-counters", Static).update(
            f"{self._successful} succeeded  ·  {self._failed} failed"
        )

        result_widget = self.query_one("#current-result", Static)
        if result.status.is_completed:
            change = format_size_change(
                result.original_size, result.compressed_size or 0
            )
            result_widget.update(
                f"{format_mb(result.original_size)} \u2192 {format_mb(result.compressed_size or 0)}  ({change})"
            )
        elif result.error:
            result_widget.update(f"[red]{result.error}[/red]")

    def _finish(self, batch: BatchResult) -> None:
        self.app.pop_screen()
        self.app.push_screen(ReportScreen(batch))

    def action_cancel(self) -> None:
        if not self.cancel_event.is_set():
            logger.info(
                "User requested batch cancellation (%d job(s) queued).", len(self.jobs)
            )
            self.cancel_event.set()
            self.query_one("#current-result", Static).update(
                "[yellow]Cancelling after the current file…[/yellow]"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-button":
            self.action_cancel()


class ReportScreen(Screen):
    """Screen 3: final summary and a per-file results table."""

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit_app", "Quit"),
        ("n", "new_batch", "New batch"),
    ]

    def __init__(self, batch: BatchResult) -> None:
        super().__init__()
        self.batch = batch
        self._results_by_row: dict[RowKey, CompressionResult] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="report-body"):
            yield Static("PDFXZ REPORT", id="report-title")
            yield Static(self._summary_text(), id="report-summary")
            yield DataTable(id="report-table")
            yield Static("", id="selected-file-path")
        with Horizontal(id="report-actions"):
            yield Button("New batch", id="new-batch-button", variant="primary")
            yield Button("Quit", id="quit-button", variant="error")
        yield Footer()

    def _summary_text(self) -> str:
        batch = self.batch
        lines = [
            f"Files discovered   {batch.total}",
            f"Successful         {batch.successful}",
            f"Failed             {batch.failed}",
        ]
        if batch.skipped:
            lines.append(f"Skipped (invalid)  {batch.skipped}")
        if batch.cancelled_count:
            lines.append(f"Cancelled          {batch.cancelled_count}")
        lines += [
            "",
            f"Original size      {format_mb(batch.original_size)}",
            f"Compressed size    {format_mb(batch.compressed_size)}",
            f"Total saved        {format_mb(batch.saved_bytes)}",
            f"Reduction          {batch.reduction_percent:.2f}%",
            f"Elapsed time       {format_duration(batch.elapsed_seconds)}",
        ]
        largest = batch.largest_saving
        if largest and largest.saved_bytes > 0:
            lines += [
                "",
                f"Largest saving: {truncate_filename(largest.input_path.name)}   -{format_mb(largest.saved_bytes)}",
            ]
        return "\n".join(lines)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("File", width=_FILENAME_COLUMN_WIDTH)
        table.add_column("Status", width=10)
        table.add_column("Before", width=10)
        table.add_column("After", width=10)
        table.add_column("Saved", width=12)
        for result in self.batch.results:
            if result.status.is_completed:
                saved = f"{result.reduction_percent:.0f}%"
            elif result.status == CompressionStatus.SKIPPED:
                saved = "invalid"
            elif result.status == CompressionStatus.CANCELLED:
                saved = "--"
            else:
                saved = "error"
            row_key = table.add_row(
                truncate_filename(result.input_path.name, _FILENAME_COLUMN_WIDTH),
                _STATUS_LABELS[result.status],
                format_mb(result.original_size) if result.original_size else "--",
                format_mb(result.compressed_size)
                if result.compressed_size is not None
                else "--",
                saved,
            )
            self._results_by_row[row_key] = result
        if self.batch.results:
            self._show_full_path(self.batch.results[0])

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        result = self._results_by_row.get(event.row_key)
        if result is not None:
            self._show_full_path(result)

    def _show_full_path(self, result: CompressionResult) -> None:
        # DataTable has no per-cell tooltip support, so the full path (and,
        # for a failed/skipped file, the reason) is surfaced here instead -
        # the nearest equivalent this framework offers to a hover tooltip.
        text = str(result.input_path)
        if not result.status.is_completed and result.error:
            text = f"{text}  \u2014  {result.error}"
        self.query_one("#selected-file-path", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-button":
            self.app.exit()
        elif event.button.id == "new-batch-button":
            self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_new_batch(self) -> None:
        self.app.pop_screen()


class PDFXZApp(App):
    """The pdfxz Textual application."""

    CSS_PATH = "app.tcss"
    TITLE = "pdfxz"

    def on_mount(self) -> None:
        self.push_screen(ConfigScreen())

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        # Drop the built-in "Screenshot" command - it has no relevance to
        # pdfxz and isn't something we want to support/maintain. Every
        # other default system command (Theme, Quit, Keys, Maximize/...)
        # is left intact.
        for command in super().get_system_commands(screen):
            if command.title == "Screenshot":
                continue
            yield command


def run() -> None:  # pragma: no cover - thin convenience wrapper
    PDFXZApp().run()
