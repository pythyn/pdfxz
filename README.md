# pdfxz

A terminal UI and CLI for compressing PDF files with [Ghostscript](https://www.ghostscript.com/).

```
┌───────────────────────────────────────────────────────────────┐
│ PDFXZ                                                         │
│ PDF Compression Utility                                       │
├───────────────────────────────────────────────────────────────┤
│  INPUT  (a PDF file or a directory)                           │
│  [ ~/Documents/papers                                    ]    │
│                                                               │
│  OUTPUT (optional - a sensible default is used if left blank) │
│  [ ~/Documents/compressed                                ]    │
│                                                               │
│  QUALITY                                                      │
│  [ Balanced ▼ ]                                               │
│                                                               │
│                                                               │
│                                                               │
│                     [ Compress PDFs ]                         │
├───────────────────────────────────────────────────────────────┤
│ Status: Ready                                                 │
└───────────────────────────────────────────────────────────────┘
```

## Features

- **Interactive TUI** for point-and-shoot use - no CLI syntax to memorize.
- **Non-interactive CLI** for scripts, cron jobs, and CI.
- **Five explicit compression profiles**, from archival quality to maximum size reduction.
- **Batch directory processing** with optional recursion, one bad file never aborts the batch.
- **Live, honest progress** - per-file counts and results, no fabricated percentages.
- **Cancellable** mid-batch, with automatic cleanup of partial output.
- **Data-safe by default**: never overwrites the input, never silently clobbers an existing output.
- **Cross-platform**: Linux, macOS, and Windows, wherever Python and Ghostscript are available.

## Installation

```bash
pip install pdfxz
```

or, from a local checkout:

```bash
pip install .
```

### Ghostscript requirement

pdfxz compresses PDFs *using* Ghostscript, but does not bundle it. Install Ghostscript separately and make sure it's on your `PATH`:

| Platform | Command |
| --- | --- |
| Ubuntu / Debian | `sudo apt install ghostscript` |
| Fedora | `sudo dnf install ghostscript` |
| Arch Linux | `sudo pacman -S ghostscript` |
| macOS (Homebrew) | `brew install ghostscript` |
| Windows | Download the installer from [ghostscript.com](https://www.ghostscript.com/releases/gsdnld.html) |

On Windows, pdfxz looks for `gswin64c`, `gswin32c`, or `gs` on `PATH` (the console builds, not the GUI `gswin64.exe`). You can also point pdfxz at a specific binary with the `PDFXZ_GS_PATH` environment variable.

If Ghostscript isn't found, pdfxz tells you clearly instead of failing with a cryptic error.

## Usage

### TUI

```bash
pdfxz
```

Pick an input PDF or folder and, optionally, a destination folder - either by typing a path or using the **Browse…** buttons, which open a built-in folder/file browser. Drag the **Quality** slider (arrow keys or click) to choose a compression profile. Directories are always scanned recursively, missing output folders are created automatically, and an existing output is never overwritten - a uniquely-named file (`report_compressed (2).pdf`, etc.) is written alongside it instead, so there's nothing to configure and nothing you can accidentally clobber.

Keyboard shortcuts (also shown at the bottom of the screen): `Esc` cancels a running batch; `q` quits (when a text field isn't focused); on the report screen, `n` starts a new batch. Long filenames are truncated in the UI - highlight a row in the report table to see the full path underneath it.

### CLI

```bash
pdfxz paper.pdf                              # -> paper_compressed.pdf
pdfxz input.pdf output.pdf                   # explicit output (positional)
pdfxz input.pdf -o output.pdf                # explicit output (flag)
pdfxz ~/papers -o ~/compressed                # compress a whole directory
pdfxz ~/papers -o ~/compressed --quality balanced
pdfxz ~/papers -o ~/compressed -q strong -r   # recurse into subdirectories
pdfxz input.pdf -o ~/new/path/out.pdf -p      # create missing output dirs
```

```
usage: pdfxz [-h] [-o PATH] [-p] [-q LEVEL] [-r] [--overwrite] [--no-tui]
             [--debug] [--version]
             [INPUT] [OUTPUT]

positional arguments:
  INPUT                 A PDF file or a directory containing PDFs.
  OUTPUT                Output PDF file or directory (positional form).

options:
  -h, --help            show this help message and exit
  -o PATH, --output PATH
                        Output PDF file or directory.
  -p, --parents         Create missing output directories (like 'mkdir -p').
  -q LEVEL, --quality LEVEL
                        Compression profile: balanced, high, maximum,
                        maximum-compression, strong (default: balanced).
  -r, --recursive       Recurse into subdirectories when INPUT is a directory
                        (default: off, top level only).
  --overwrite           Allow overwriting an existing output file.
  --no-tui              Never launch the interactive TUI; exit with an error
                        if INPUT is missing instead of prompting.
  --debug               Enable verbose debug logging.
  --version             show program's version number and exit
```

Running `pdfxz` with no arguments launches the TUI. Passing `INPUT` runs non-interactively - the TUI never blocks a script. `--no-tui` is a safety net for automation: if a script accidentally omits `INPUT`, pdfxz fails fast with a clear error instead of trying to open an interactive terminal.

Exit codes: `0` on full success, `1` if any file failed, was skipped as invalid, or was cancelled, `2` on a usage error, `130` on Ctrl+C.

## Compression profiles

Ghostscript's built-in `/screen`, `/ebook`, `/printer`, `/prepress` presets aren't used directly - their exact behavior has varied across Ghostscript versions. Instead, pdfxz defines five explicit, documented profiles built around image downsampling:

| Level | Color/Gray DPI | Mono DPI | Goal |
| --- | --- | --- | --- |
| Maximum Quality | 300 | 1200 | Minimal quality loss; archival copies |
| High Quality | 200 | 600 | Good visual quality, moderate compression |
| Balanced *(default)* | 150 | 300 | General-purpose default |
| Strong Compression | 120 | 200 | Smaller files, visible trade-off |
| Maximum Compression | 72 | 150 | Prioritizes file size |

No profile guarantees a specific percentage reduction - actual results depend heavily on the PDF's contents (image-heavy scans compress far more than text-only documents).

## Batch processing & output naming

- **Single file**: `paper.pdf` -> `paper_compressed.pdf` by default, or your chosen output path.
- **Directory**: each discovered PDF gets a `..._compressed.pdf` sibling under the output directory.
- **Recursive scans**: pdfxz preserves the input's relative directory structure under the output directory, so `papers/a/report.pdf` and `papers/b/report.pdf` never collide or overwrite each other.
- One failed or invalid file never aborts the batch - it's recorded and processing continues.

## Output & overwrite behavior

- pdfxz never overwrites the input file, and rejects any operation where input and output resolve to the same file.
- An existing output file is left untouched unless you pass `--overwrite` (CLI) or check "Overwrite existing output" (TUI).
- Missing output directories are only created if you pass `-p/--parents` (CLI) or leave "Create missing directories" checked (TUI, on by default).
- If Ghostscript fails or is cancelled partway through, any partial output file is deleted; the input is never touched.

## Defaults

| Setting | Default |
| --- | --- |
| Quality | `balanced` |
| Recursive | off (top-level only) |
| Create missing directories | on (TUI) / off (CLI, use `-p`) |
| Overwrite | off |

## Troubleshooting

**"Ghostscript is not installed"** - install it and confirm `gs --version` (or `gswin64c --version` on Windows) works in your terminal.

**"Output file already exists"** - pass `--overwrite`, or choose a different output path.

**"Output path is the same as the input path"** - choose a distinct output location; pdfxz refuses to overwrite the source PDF.

**"No PDF files found"** - check that files actually end in `.pdf` (case-insensitive) and, for nested folders, that you passed `-r/--recursive`.

**A file is reported invalid** - pdfxz checks the `%PDF-` signature, not just the extension; the file may be corrupt or not actually a PDF.

## Development

```bash
git clone https://github.com/example/pdfxz
cd pdfxz
python -m venv .venv
source .venv/bin/activate          # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

### Project layout

```
src/pdfxz/
├── __init__.py           # package version
├── __main__.py           # `python -m pdfxz` entry point
├── cli.py                # argument parsing + non-interactive execution
├── app.py                # Textual TUI (config / processing / report screens)
├── app.tcss              # TUI stylesheet
├── compressor.py         # Ghostscript subprocess integration
├── workers.py            # framework-agnostic batch orchestration (shared by CLI + TUI)
├── scanner.py            # PDF discovery + %PDF- signature validation
├── models.py             # typed result/state dataclasses
├── profiles.py           # the five compression profiles
├── formatting.py         # size/percentage/ratio/duration helpers
└── utils.py              # Ghostscript discovery, path safety, output planning
```

The compressor has no knowledge of the TUI or CLI; the scanner has no knowledge of Ghostscript; the TUI and CLI both drive the same `BatchRunner`. This keeps each layer independently testable.

### Testing

```bash
pytest
```

The test suite mocks Ghostscript with a small fake executable (`tests/fixtures/fake_gs.py`), so it never requires a real Ghostscript installation. It covers the scanner, compressor (including cancellation and cleanup), profiles, formatting helpers, the CLI, and a TUI smoke test.

## License

MIT - see [LICENSE](LICENSE).
