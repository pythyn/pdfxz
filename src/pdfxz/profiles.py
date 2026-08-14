"""Explicit compression profiles.

Ghostscript ships coarse presets (``/screen``, ``/ebook``, ``/printer``,
``/prepress``) via ``-dPDFSETTINGS``. Their exact numeric behaviour has
drifted across Ghostscript versions and is not documented as stable, so
pdfxz does not rely on them. Instead every user-facing quality level maps
to an explicit, versioned set of Ghostscript switches defined here. This
keeps behaviour predictable and testable independent of the Ghostscript
version installed on a given machine.

The five profiles differ primarily in image downsampling resolution and
threshold, which is the single biggest lever on output size for
typical (figure- and scan-heavy) academic PDFs. ``balanced`` intentionally
reproduces the resolution values used by the original reference
implementation (150/150/300 DPI), so it behaves as a drop-in default.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompressionProfile:
    """A named, documented set of Ghostscript image-handling settings."""

    key: str
    label: str
    description: str
    color_image_resolution: int
    gray_image_resolution: int
    mono_image_resolution: int
    downsample_threshold: float = 1.5
    color_downsample_type: str = "/Bicubic"
    gray_downsample_type: str = "/Bicubic"
    mono_downsample_type: str = "/Bicubic"

    def gs_args(self) -> list[str]:
        """Ghostscript arguments implementing this profile.

        Does not include ``-sOutputFile`` or the input path; the compressor
        appends those separately so this method stays a pure function of
        the profile.
        """
        return [
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.6",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dEmbedAllFonts=true",
            "-dDetectDuplicateImages=true",
            "-dDoThumbnails=false",
            "-dCreateJobTicket=false",
            "-dPreserveEPSInfo=false",
            "-dPreserveOPIComments=false",
            "-dPreserveOverprintSettings=false",
            "-dUCRandBGInfo=/Remove",
            "-dDownsampleColorImages=true",
            f"-dColorImageDownsampleType={self.color_downsample_type}",
            f"-dColorImageResolution={self.color_image_resolution}",
            f"-dColorImageDownsampleThreshold={self.downsample_threshold}",
            "-dDownsampleGrayImages=true",
            f"-dGrayImageDownsampleType={self.gray_downsample_type}",
            f"-dGrayImageResolution={self.gray_image_resolution}",
            f"-dGrayImageDownsampleThreshold={self.downsample_threshold}",
            "-dDownsampleMonoImages=true",
            f"-dMonoImageDownsampleType={self.mono_downsample_type}",
            f"-dMonoImageResolution={self.mono_image_resolution}",
            f"-dMonoImageDownsampleThreshold={self.downsample_threshold}",
        ]


QUALITY_PROFILES: dict[str, CompressionProfile] = {
    "maximum": CompressionProfile(
        key="maximum",
        label="Maximum Quality",
        description=(
            "Minimal quality loss. Only unusually high-resolution images are "
            "downsampled; intended for archival copies."
        ),
        color_image_resolution=300,
        gray_image_resolution=300,
        mono_image_resolution=1200,
        downsample_threshold=2.0,
    ),
    "high": CompressionProfile(
        key="high",
        label="High Quality",
        description="Good visual quality with moderate compression; suitable for print-quality figures.",
        color_image_resolution=200,
        gray_image_resolution=200,
        mono_image_resolution=600,
        downsample_threshold=1.5,
    ),
    "balanced": CompressionProfile(
        key="balanced",
        label="Balanced",
        description="General-purpose default. Matches typical screen/print needs.",
        color_image_resolution=150,
        gray_image_resolution=150,
        mono_image_resolution=300,
        downsample_threshold=1.5,
    ),
    "strong": CompressionProfile(
        key="strong",
        label="Strong Compression",
        description="Smaller files with a visible, but usually acceptable, quality trade-off.",
        color_image_resolution=120,
        gray_image_resolution=120,
        mono_image_resolution=200,
        downsample_threshold=1.3,
    ),
    "maximum-compression": CompressionProfile(
        key="maximum-compression",
        label="Maximum Compression",
        description="Prioritizes file size above all else; images will show noticeable quality loss.",
        color_image_resolution=72,
        gray_image_resolution=72,
        mono_image_resolution=150,
        downsample_threshold=1.0,
    ),
}

DEFAULT_QUALITY = "balanced"


def get_profile(key: str) -> CompressionProfile:
    """Look up a profile by key, raising a clear error for unknown keys."""
    try:
        return QUALITY_PROFILES[key]
    except KeyError as exc:
        valid = ", ".join(sorted(QUALITY_PROFILES))
        raise KeyError(
            f"Unknown quality profile '{key}'. Valid options: {valid}"
        ) from exc
