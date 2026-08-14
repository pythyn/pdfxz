# Changelog

All notable changes to this project are documented in this file.

## [0.2.1]

### Changed
- TUI redesigned to be more compact and minimal: smaller fields/buttons, a
  larger/bolder title, and a volume-control-style slider.
- TUI's Input/Output fields now have a **Browse…** button that opens a
  built-in folder/file picker (`textual.widgets.DirectoryTree`-based), so
  typing a full path is no longer required.
- TUI dropped the Recursive / Create-missing-directories / Overwrite
  checkboxes in favor of automatic, safe defaults: directories are always
  scanned recursively, missing output directories are always created, and
  an existing output file is never overwritten - a uniquely-named sibling
  file is written instead (`utils.unique_output_path`). The CLI's
  `-r/--recursive`, `-p/--parents`, and `--overwrite` flags are unchanged.
- TUI file sizes are now always shown in MB (`formatting.format_mb`)
  instead of switching units; the CLI's multi-unit report is unchanged.
- TUI filenames are now truncated to a fixed width with an ellipsis
  (`formatting.truncate_filename`); the full path is shown when a report
  table row is highlighted, since `DataTable` has no per-cell tooltip.
- Removed the built-in "Screenshot" command from the TUI's command
  palette (`PDFXZApp.get_system_commands`); all other default commands
  (Quit, Theme, etc.) are unchanged.

### Fixed
- Test collection failure (`ModuleNotFoundError: No module named 'tests'`)
  when running the suite via the bare `pytest` command instead of
  `python -m pytest`. Root cause: `tests/` has no `__init__.py`, so
  `tests.conftest` was only importable when the project root happened to
  already be on `sys.path`. Fixed by importing `conftest` directly, which
  pytest's own rootless-test-directory handling already supports
  regardless of invocation method or working directory.
- The processing screen's `Ctrl+C` cancel shortcut never actually fired:
  Textual's `App` binds `ctrl+c` to its own `help_quit` action with
  `priority=True`, which silently pre-empts any Screen-level binding for
  the same key. `Escape` was the only shortcut that ever worked; `Ctrl+C`
  is no longer advertised as a cancel shortcut since it wasn't one.

## [0.1.0] - Initial release

### Added
- Interactive Textual TUI: configuration screen, live processing screen with
  cancellable progress, and a scrollable final report screen.
- Non-interactive CLI supporting single-file and directory (batch) modes,
  with `-o/--output`, `-p/--parents`, `-q/--quality`, `-r/--recursive`,
  `--overwrite`, `--no-tui`, `--debug`, `--version`.
- Five explicit compression profiles (`maximum`, `high`, `balanced`,
  `strong`, `maximum-compression`) built on documented Ghostscript
  image-downsampling settings rather than the `/screen`-style presets.
- Ghostscript discovery across Linux, macOS, and Windows, including
  `PDFXZ_GS_PATH` override support.
- PDF signature (`%PDF-`) validation independent of file extension.
- Collision-safe batch output planning that preserves relative directory
  structure for recursive scans.
- Automatic partial-output cleanup on failure or cancellation; the
  original input file is never modified or deleted.
- Full pytest suite (scanner, compressor, profiles, formatting, CLI, and a
  TUI smoke test) that mocks Ghostscript and never requires it to be
  installed.
