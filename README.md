# pdfxz

**Simple PDF compression from your terminal.**

`pdfxz` is a small command-line tool for compressing PDF files with [Ghostscript](https://www.ghostscript.com/).

It gives you two ways to work:

* **Interactive TUI** — easy to use with menus and buttons.
* **CLI** — great for scripts, batch jobs, and automation.

```text
┌───────────────────────────────────────────────────────────────┐
│                         P D F X Z                             │
│                  PDF Compression Utility                      │
├───────────────────────────────────────────────────────────────┤
│ INPUT                                                         │
│ [ ~/Documents/papers                          ] [ Browse... ] │
│                                                               │
│ OUTPUT                                                        │
│ [ ~/Documents/compressed                      ] [ Browse... ] │
│                                                               │
│ QUALITY                                                       │
│ ▰▰▰▯▯  Balanced                                               │
│                                                               │
│                     [ Compress PDFs ]                         │
└───────────────────────────────────────────────────────────────┘
```

## Why pdfxz?

* **Easy to use:** run `pdfxz` and use the interactive interface.
* **Works without the TUI:** use simple commands for scripts and automation.
* **Compress one file or many:** process a PDF or an entire folder.
* **Five clear quality levels:** choose how much compression you want.
* **Safe by default:** your original PDF is never overwritten.
* **Safe batch processing:** one bad PDF does not stop the other files.
* **Automatic cleanup:** incomplete output files are removed after failure or cancellation.
* **Built-in file browser:** use **Browse...** instead of typing long paths.
* **Clear progress:** see which files finished and how much space was saved.
* **Linux, macOS, and Windows:** works wherever Python and Ghostscript are available.

## Installation

### 1. Install pdfxz

```bash
pip install pdfxz
```

To install from a local checkout:

```bash
pip install .
```

`pdfxz` requires **Python 3.10 or newer**.

### 2. Install Ghostscript

`pdfxz` uses Ghostscript to do the actual PDF compression, so Ghostscript must be installed separately.

#### Ubuntu / Debian

```bash
sudo apt install ghostscript
```

#### Fedora

```bash
sudo dnf install ghostscript
```

#### Arch Linux

```bash
sudo pacman -S ghostscript
```

#### macOS

Using Homebrew:

```bash
brew install ghostscript
```

#### Windows

Download and install Ghostscript from:

https://www.ghostscript.com/releases/gsdnld.html

On Windows, `pdfxz` looks for `gswin64c`, `gswin32c`, or `gs` on `PATH`. You can also set `PDFXZ_GS_PATH` when Ghostscript is installed somewhere else.

Check that Ghostscript works:

```bash
gs --version
```

On Windows, you can use:

```powershell
gswin64c --version
```

If Ghostscript is missing, `pdfxz` shows a clear error instead of a confusing failure.

---

## How to Use

### Interactive TUI

The easiest way to start:

```bash
pdfxz
```

Choose your input PDF or folder, choose an output folder if needed, select a quality level, and press **Compress PDFs**.

### Browse files and folders

The TUI includes **Browse...** buttons for both input and output.

You can select:

* a PDF file
* an input folder
* an output folder

You do not need to type the complete path yourself.

### v0.2.1: fewer settings, less to worry about

The TUI no longer asks you to manually configure:

* Recursive scanning
* Create missing directories
* Overwrite existing files

These are handled automatically:

* folders are always scanned **recursively**
* missing output folders are created automatically
* existing output files are **never overwritten**
* when a filename already exists, pdfxz creates a new unique filename instead

The CLI still provides explicit options for these settings.

### File sizes

The TUI always displays file sizes in **MB** for a consistent view.

### Useful TUI shortcuts

* `Esc` — cancel a running batch
* `q` — quit
* `n` — start a new batch from the report screen

Long filenames are shortened on screen. Select a report row to see the full path.

---

## CLI

The CLI is useful when you want commands that can be reused in scripts.

### Compress one PDF

```bash
pdfxz paper.pdf
```

Creates:

```text
paper_compressed.pdf
```

### Choose the output file

```bash
pdfxz input.pdf -o output.pdf
```

You can also use the positional form:

```bash
pdfxz input.pdf output.pdf
```

### Compress a folder

```bash
pdfxz ~/papers -o ~/compressed
```

### Choose a quality level

```bash
pdfxz paper.pdf -q balanced
```

### Scan subdirectories

```bash
pdfxz ~/papers -o ~/compressed -q strong -r
```

### Create missing output directories

```bash
pdfxz input.pdf -o ~/new/path/output.pdf -p
```

### Never start the TUI

For scripts and automation:

```bash
pdfxz input.pdf --no-tui
```

When `INPUT` is supplied, pdfxz already runs non-interactively. `--no-tui` is useful when you want a script to fail immediately instead of opening the interactive interface by mistake.

---

## Common CLI Options

| Option                | What it does                                 |
| --------------------- | -------------------------------------------- |
| `-o, --output PATH`   | Set the output PDF or directory              |
| `-p, --parents`       | Create missing output directories            |
| `-q, --quality LEVEL` | Choose the compression level                 |
| `-r, --recursive`     | Scan subdirectories too                      |
| `--overwrite`         | Allow an existing output file to be replaced |
| `--no-tui`            | Never launch the interactive interface       |

The available quality values are `maximum`, `high`, `balanced`, `strong`, and `maximum-compression`.

---

## Compression Levels

`pdfxz` has five explicit compression profiles. The default is **Balanced**.

| Level                 | Best for                        | Quality   | Compression |
| --------------------- | ------------------------------- | --------- | ----------- |
| `maximum`             | Archival copies                 | Highest   | Lowest      |
| `high`                | Good quality with smaller files | Very high | Moderate    |
| `balanced`            | Everyday use                    | Good      | Moderate    |
| `strong`              | Smaller files                   | Lower     | Strong      |
| `maximum-compression` | Smallest possible files         | Lowest    | Highest     |

The profiles use different image downsampling settings. Higher compression generally means smaller files and more visible quality loss.

### Important

There is no fixed compression percentage.

A scanned PDF with many images may become much smaller, while a text-only PDF may change very little.

---

## Safe Output and File Naming

`pdfxz` is designed to keep your files safe.

### Your original PDF is never overwritten

The compressor refuses to use the same file as both input and output. The original input is never modified or deleted.

### Existing files are protected

In the CLI, an existing output is not replaced unless you explicitly use:

```bash
--overwrite
```

In the TUI, existing outputs are never overwritten; pdfxz creates a unique filename instead.

For example:

```text
report.pdf
report_compressed.pdf
report_compressed (2).pdf
report_compressed (3).pdf
```

### Batch folders stay organized

When scanning folders recursively, pdfxz keeps the original folder structure in the output directory. This prevents files with the same name in different folders from accidentally replacing each other.

### Failed or cancelled jobs are cleaned up

If Ghostscript fails or you cancel a compression, pdfxz removes any partial output file. Your input PDF remains untouched.

### Invalid PDFs are detected

pdfxz does not trust the `.pdf` extension alone. It also checks for the `%PDF-` file signature.

---

## Development

Clone the repository:

```bash
git clone https://github.com/pythyn/pdfxz
cd pdfxz
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

Linux / macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

Install the development dependencies:

```bash
pip install -e ".[dev]"
```

The project uses `pytest` and `pytest-asyncio` for development and testing.

## Testing

Run the full test suite:

```bash
pytest
```

The tests cover the main parts of the project, including:

* TUI startup and interaction
* CLI parsing and execution
* PDF compression
* cancellation and cleanup
* compression profiles
* file scanning and PDF validation
* formatting and utility functions

The test suite uses a small fake Ghostscript executable, so the tests do **not** need a real Ghostscript installation.

The v0.2.1 tests also verify that the old TUI settings for recursive scanning, missing directories, and overwrite behavior are no longer present.

## Project Structure

```text
pdfxz/
├── src/pdfxz/
│   ├── app.py           # Interactive TUI
│   ├── cli.py           # Command-line interface
│   ├── compressor.py    # Ghostscript compression
│   ├── profiles.py      # Compression profiles
│   ├── scanner.py       # PDF discovery and validation
│   ├── workers.py       # Batch processing
│   ├── models.py        # Result and state models
│   ├── formatting.py    # Output formatting helpers
│   └── utils.py         # Paths, Ghostscript, and safety helpers
│
├── tests/
│   ├── test_app.py
│   ├── test_cli.py
│   ├── test_compressor.py
│   ├── test_profiles.py
│   ├── test_scanner.py
│   ├── test_utils.py
│   ├── test_formatting.py
│   └── fixtures/
│       └── fake_gs.py
│
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

The TUI and CLI use the same underlying compression and batch-processing code, which keeps behavior consistent between both modes.

## License

MIT License.

See [LICENSE](LICENSE) for the full license text.
