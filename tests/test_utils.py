from __future__ import annotations

from pdfxz.utils import plan_batch_outputs, plan_single_output, unique_output_path


class TestUniqueOutputPath:
    def test_returns_path_unchanged_when_free(self, tmp_path):
        target = tmp_path / "report_compressed.pdf"
        assert unique_output_path(target) == target

    def test_appends_numeric_suffix_on_collision(self, tmp_path):
        target = tmp_path / "report_compressed.pdf"
        target.write_bytes(b"existing")
        result = unique_output_path(target)
        assert result == tmp_path / "report_compressed (2).pdf"

    def test_increments_past_multiple_collisions(self, tmp_path):
        target = tmp_path / "report_compressed.pdf"
        target.write_bytes(b"one")
        (tmp_path / "report_compressed (2).pdf").write_bytes(b"two")
        (tmp_path / "report_compressed (3).pdf").write_bytes(b"three")
        result = unique_output_path(target)
        assert result == tmp_path / "report_compressed (4).pdf"

    def test_never_overwrites_original_input(self, tmp_path):
        # The whole point: an existing file is never silently reused as
        # the output target.
        target = tmp_path / "report_compressed.pdf"
        original_content = b"do not touch me"
        target.write_bytes(original_content)
        result = unique_output_path(target)
        assert result != target
        assert target.read_bytes() == original_content


class TestPlanSingleOutput:
    def test_default_name_when_no_output_given(self, tmp_path):
        input_path = tmp_path / "paper.pdf"
        assert plan_single_output(input_path, None) == tmp_path / "paper_compressed.pdf"

    def test_explicit_file_target_used_as_is(self, tmp_path):
        input_path = tmp_path / "paper.pdf"
        output = tmp_path / "custom_name.pdf"
        assert plan_single_output(input_path, output) == output

    def test_existing_directory_target_gets_default_filename(self, tmp_path):
        input_path = tmp_path / "paper.pdf"
        out_dir = tmp_path / "dest"
        out_dir.mkdir()
        assert (
            plan_single_output(input_path, out_dir) == out_dir / "paper_compressed.pdf"
        )


class TestPlanBatchOutputs:
    def test_preserves_relative_structure_to_avoid_collisions(self, tmp_path):
        source_root = tmp_path / "papers"
        a = source_root / "a" / "report.pdf"
        b = source_root / "b" / "report.pdf"
        output_root = tmp_path / "out"

        mapping = plan_batch_outputs([a, b], source_root, output_root)

        assert mapping[a] == output_root / "a" / "report_compressed.pdf"
        assert mapping[b] == output_root / "b" / "report_compressed.pdf"
        assert mapping[a] != mapping[b]
