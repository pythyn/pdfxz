from __future__ import annotations

import pytest

from pdfxz.profiles import DEFAULT_QUALITY, QUALITY_PROFILES, get_profile


def test_five_profiles_defined():
    assert len(QUALITY_PROFILES) == 5


def test_default_quality_is_valid_key():
    assert DEFAULT_QUALITY in QUALITY_PROFILES


def test_profiles_have_distinct_labels():
    labels = [p.label for p in QUALITY_PROFILES.values()]
    assert len(labels) == len(set(labels))


def test_profiles_have_distinct_resolutions():
    # Section 10 requires levels not just be identically-labeled duplicates.
    resolutions = [
        (p.color_image_resolution, p.gray_image_resolution, p.mono_image_resolution)
        for p in QUALITY_PROFILES.values()
    ]
    assert len(resolutions) == len(set(resolutions))


def test_maximum_quality_uses_highest_resolution():
    profiles = QUALITY_PROFILES
    assert (
        profiles["maximum"].color_image_resolution
        > profiles["balanced"].color_image_resolution
    )
    assert (
        profiles["balanced"].color_image_resolution
        > profiles["maximum-compression"].color_image_resolution
    )


def test_balanced_matches_reference_implementation_defaults():
    # The Bash reference implementation hardcoded 150/150/300 DPI.
    balanced = QUALITY_PROFILES["balanced"]
    assert balanced.color_image_resolution == 150
    assert balanced.gray_image_resolution == 150
    assert balanced.mono_image_resolution == 300


def test_gs_args_contains_required_switches():
    args = QUALITY_PROFILES["balanced"].gs_args()
    required = [
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
    ]
    for switch in required:
        assert switch in args


def test_gs_args_reflects_profile_resolution():
    profile = QUALITY_PROFILES["strong"]
    args = profile.gs_args()
    assert f"-dColorImageResolution={profile.color_image_resolution}" in args
    assert f"-dGrayImageResolution={profile.gray_image_resolution}" in args
    assert f"-dMonoImageResolution={profile.mono_image_resolution}" in args


def test_gs_args_does_not_include_output_or_input():
    # -sOutputFile and the input path are appended by the compressor, not the profile.
    args = QUALITY_PROFILES["balanced"].gs_args()
    assert not any(a.startswith("-sOutputFile=") for a in args)


def test_get_profile_valid_key():
    assert get_profile("balanced").key == "balanced"


def test_get_profile_invalid_key_raises():
    with pytest.raises(KeyError):
        get_profile("ultra-mega-compression")
