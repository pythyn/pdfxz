"""Cross-platform utilities that don't belong to a single layer.

Covers: Ghostscript executable discovery, safe same-file detection,
output-directory creation, default output naming, and batch output
planning (collision-safe for recursive scans). No Textual imports here -
the CLI and TUI both depend on this module, not the other way around.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from pathlib import Path

logger = logging.getLogger("pdfxz")


def configure_logging(debug: bool = False) -> None:
    """Configure the 'pdfxz' logger.

    Normal runs stay quiet (WARNING+) so the TUI/CLI output isn't spammed;
    --debug switches to verbose DEBUG logging for troubleshooting.
    """
    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s", "%H:%M:%S"
        )
    )

    root = logging.getLogger("pdfxz")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


# --------------------------------------------------------------------------
# Ghostscript discovery
# --------------------------------------------------------------------------

_CANDIDATE_NAMES_POSIX = ("gs",)
# Ghostscript on Windows ships as gswin64c.exe / gswin32c.exe (console builds);
# gswin64.exe / gswin32.exe are GUI builds and unsuitable for subprocess use.
_CANDIDATE_NAMES_WINDOWS = ("gswin64c", "gswin32c", "gs")


def locate_ghostscript(explicit_path: str | None = None) -> str | None:
    """Find a usable Ghostscript executable.

    Resolution order: an explicitly supplied path/name, the
    ``PDFXZ_GS_PATH`` environment variable, then a platform-appropriate
    list of well-known executable names on PATH. Returns None if nothing
    usable is found - callers are responsible for reporting that clearly.
    """
    if explicit_path:
        return shutil.which(explicit_path) or (
            explicit_path if Path(explicit_path).is_file() else None
        )

    env_override = os.environ.get("PDFXZ_GS_PATH")
    if env_override:
        found = shutil.which(env_override) or (
            env_override if Path(env_override).is_file() else None
        )
        if found:
            return found

    names = (
        _CANDIDATE_NAMES_WINDOWS
        if platform.system() == "Windows"
        else _CANDIDATE_NAMES_POSIX
    )
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


# --------------------------------------------------------------------------
# Path safety
# --------------------------------------------------------------------------


def is_same_path(path_a: Path, path_b: Path) -> bool:
    """Robustly determine whether two paths refer to the same filesystem object.

    Prefers ``os.path.samefile`` (handles symlinks/hardlinks correctly) when
    both paths exist, and falls back to comparing resolved paths when the
    output does not exist yet - the common case, since output files are
    usually created fresh.
    """
    try:
        if path_a.exists() and path_b.exists():
            return os.path.samefile(path_a, path_b)
    except OSError:
        pass
    try:
        return path_a.resolve() == path_b.resolve()
    except OSError:
        return str(path_a.absolute()) == str(path_b.absolute())


def ensure_parent_dir(path: Path, create_parents: bool) -> None:
    """Ensure the parent directory of `path` exists.

    Raises OSError/FileNotFoundError with an actionable message on failure;
    never silently swallows a directory-creation failure.
    """
    parent = path.parent
    if str(parent) in ("", ".") or parent.exists():
        return
    if not create_parents:
        raise FileNotFoundError(
            f"Output directory does not exist: {parent}\n"
            "Pass -p/--parents (CLI) or enable 'Create missing directories' (TUI) to create it automatically."
        )
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Failed to create output directory '{parent}': {exc}") from exc


# --------------------------------------------------------------------------
# Output naming / planning
# --------------------------------------------------------------------------


def default_output_name(input_path: Path) -> str:
    """The default output filename for a given input, e.g. paper.pdf -> paper_compressed.pdf."""
    suffix = input_path.suffix or ".pdf"
    return f"{input_path.stem}_compressed{suffix}"


def plan_single_output(input_path: Path, output: Path | None) -> Path:
    """Resolve the output path for single-file mode.

    If no output was given, use the default sibling name. If the given
    output is an existing directory, place the default-named file inside
    it. Otherwise the given output is treated as the exact target file.
    """
    if output is None:
        return input_path.with_name(default_output_name(input_path))
    if output.is_dir():
        return output / default_output_name(input_path)
    return output


def unique_output_path(path: Path) -> Path:
    """Return `path` unchanged if it doesn't exist, otherwise a free sibling
    path with a numeric suffix: ``paper_compressed.pdf`` ->
    ``paper_compressed (2).pdf`` -> ``paper_compressed (3).pdf`` ...

    This is how the TUI resolves output collisions automatically (no
    "overwrite?" prompt): the original input is never at risk since its
    name always differs from the generated output name, and re-running a
    batch never destroys a previous run's output - it just gets a new
    name alongside it. The CLI keeps its explicit, opt-in `--overwrite`
    behaviour unchanged; this helper is TUI-only.
    """
    if not path.exists():
        return path
    parent, stem, suffix = path.parent, path.stem, path.suffix
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def plan_batch_outputs(
    inputs: list[Path], source_root: Path, output_root: Path
) -> dict[Path, Path]:
    """Map each discovered input file to a collision-safe output path.

    Recursive directory scans can surface same-named files from different
    subdirectories (e.g. ``a/report.pdf`` and ``b/report.pdf``). To avoid
    silently overwriting one with the other, the output mirrors the input's
    directory structure relative to `source_root` underneath `output_root`,
    rather than flattening everything into one directory.
    """
    mapping: dict[Path, Path] = {}
    try:
        resolved_root = source_root.resolve()
    except OSError:
        resolved_root = source_root

    for input_path in inputs:
        try:
            relative = input_path.resolve().relative_to(resolved_root)
        except (ValueError, OSError):
            relative = Path(input_path.name)
        target_dir = output_root / relative.parent
        mapping[input_path] = target_dir / default_output_name(input_path)
    return mapping
