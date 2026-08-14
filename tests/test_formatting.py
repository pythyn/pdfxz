from __future__ import annotations

from pdfxz.formatting import (
    compression_ratio,
    format_bytes,
    format_duration,
    format_mb,
    format_ratio,
    format_size_change,
    reduction_percent,
    truncate_filename,
)


class TestFormatBytes:
    def test_bytes(self):
        assert format_bytes(0) == "0 B"
        assert format_bytes(512) == "512 B"
        assert format_bytes(1023) == "1023 B"

    def test_kilobytes(self):
        assert format_bytes(1024) == "1.00 KB"
        assert format_bytes(2048) == "2.00 KB"

    def test_megabytes(self):
        assert format_bytes(1024 * 1024) == "1.00 MB"
        assert format_bytes(int(78.3 * 1024 * 1024)) == "78.30 MB"

    def test_gigabytes(self):
        assert format_bytes(1024**3) == "1.00 GB"

    def test_negative(self):
        assert format_bytes(-2048) == "-2.00 KB"


class TestFormatDuration:
    def test_seconds_only(self):
        assert format_duration(5) == "00:05"

    def test_minutes_seconds(self):
        assert format_duration(42) == "00:42"
        assert format_duration(151) == "02:31"

    def test_hours(self):
        assert format_duration(3661) == "01:01:01"

    def test_rounding(self):
        assert format_duration(41.6) == "00:42"

    def test_negative_clamped_to_zero(self):
        assert format_duration(-5) == "00:00"


class TestReductionPercent:
    def test_typical_reduction(self):
        # 245 MB -> 78 MB
        original = 245 * 1024 * 1024
        compressed = 78 * 1024 * 1024
        pct = reduction_percent(original, compressed)
        assert round(pct, 2) == 68.16

    def test_zero_change(self):
        assert reduction_percent(1000, 1000) == 0.0

    def test_increase_is_negative(self):
        assert reduction_percent(1000, 1200) == -20.0

    def test_zero_original_no_division_error(self):
        assert reduction_percent(0, 0) == 0.0
        assert reduction_percent(0, 500) == 0.0


class TestCompressionRatio:
    def test_typical_ratio(self):
        ratio = compression_ratio(245, 78)
        assert round(ratio, 2) == round(245 / 78, 2)

    def test_zero_compressed_no_division_error(self):
        assert compression_ratio(1000, 0) is None

    def test_format_ratio(self):
        assert format_ratio(3.1415) == "3.14:1"
        assert format_ratio(None) == "n/a"


class TestFormatMb:
    def test_always_uses_mb_unit(self):
        assert format_mb(500) == "0.00 MB"
        assert format_mb(1024 * 1024) == "1.00 MB"
        assert format_mb(1024 * 1024 * 1024) == "1024.00 MB"

    def test_never_switches_units_for_large_or_small_values(self):
        # Regardless of magnitude, the unit suffix is always "MB".
        for num_bytes in (0, 100, 1024, 1024 * 1024, 5 * 1024**3):
            assert format_mb(num_bytes).endswith(" MB")

    def test_custom_precision(self):
        assert format_mb(1024 * 1024, decimals=0) == "1 MB"
        assert format_mb(int(1.5 * 1024 * 1024), decimals=1) == "1.5 MB"


class TestTruncateFilename:
    def test_short_name_untouched(self):
        assert truncate_filename("short.pdf", max_length=28) == "short.pdf"

    def test_long_name_truncated_with_ellipsis(self):
        name = "a_very_long_filename_that_exceeds_the_limit.pdf"
        result = truncate_filename(name, max_length=28)
        assert len(result) == 28
        assert result.endswith("\u2026")
        assert result.startswith("a_very_long_filename_that_e")

    def test_exact_length_untouched(self):
        name = "x" * 28
        assert truncate_filename(name, max_length=28) == name

    def test_default_max_length(self):
        name = "y" * 100
        result = truncate_filename(name)
        assert len(result) == 28


class TestFormatSizeChange:
    def test_reduction(self):
        result = format_size_change(1000, 500)
        assert result.startswith("-")
        assert "50.00%" in result

    def test_increase(self):
        result = format_size_change(1000, 1200)
        assert result.startswith("+")
        assert "20.00%" in result

    def test_unchanged(self):
        assert format_size_change(1000, 1000) == "0 B (0.00%)"
