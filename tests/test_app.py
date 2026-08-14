from __future__ import annotations

import pytest
from textual.css.query import NoMatches

from pdfxz.app import ConfigScreen, DirectoryPicker, PDFXZApp, QualitySlider
from pdfxz.profiles import DEFAULT_QUALITY


@pytest.mark.asyncio
async def test_app_boots_to_config_screen(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        assert isinstance(app.screen, ConfigScreen)
        await pilot.pause()


@pytest.mark.asyncio
async def test_compress_button_disabled_until_valid_input(mock_gs, make_pdf):
    pdf = make_pdf("in.pdf")
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        button = app.screen.query_one("#compress-button")
        assert button.disabled is True

        field = app.screen.query_one("#input-field")
        field.value = str(pdf)
        field.post_message(field.Changed(field, str(pdf)))
        await pilot.pause()

        assert button.disabled is False


@pytest.mark.asyncio
async def test_manual_directory_options_are_gone(mock_gs):
    # Recursive / create-missing-dirs / overwrite checkboxes were removed
    # in favour of automatic, sensible defaults.
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        for selector in (
            "#recursive-check",
            "#parents-check",
            "#overwrite-check",
            "#quality-select",
        ):
            with pytest.raises(NoMatches):
                app.screen.query_one(selector)


@pytest.mark.asyncio
async def test_quality_slider_defaults_to_balanced(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        slider = app.screen.query_one("#quality-slider", QualitySlider)
        assert slider.value == DEFAULT_QUALITY


@pytest.mark.asyncio
async def test_quality_slider_keyboard_adjustment(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        slider = app.screen.query_one("#quality-slider", QualitySlider)
        slider.focus()
        await pilot.pause()

        start_index = slider.index
        await pilot.press("right")
        await pilot.pause()
        assert slider.index == start_index + 1
        assert slider.value == QualitySlider.KEYS[start_index + 1]

        await pilot.press("left")
        await pilot.pause()
        assert slider.index == start_index


@pytest.mark.asyncio
async def test_quality_slider_clamped_at_bounds(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        slider = app.screen.query_one("#quality-slider", QualitySlider)
        slider.focus()

        for _ in range(len(QualitySlider.KEYS) + 3):
            await pilot.press("left")
        await pilot.pause()
        assert slider.index == 0

        for _ in range(len(QualitySlider.KEYS) + 3):
            await pilot.press("right")
        await pilot.pause()
        assert slider.index == len(QualitySlider.KEYS) - 1


@pytest.mark.asyncio
async def test_browse_input_button_opens_directory_picker(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#browse-input-button")
        await pilot.pause()
        assert isinstance(app.screen, DirectoryPicker)


@pytest.mark.asyncio
async def test_directory_picker_escape_dismisses_without_selection(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        input_before = app.screen.query_one("#input-field").value

        await pilot.click("#browse-input-button")
        await pilot.pause()
        assert isinstance(app.screen, DirectoryPicker)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfigScreen)
        assert app.screen.query_one("#input-field").value == input_before


@pytest.mark.asyncio
async def test_screenshot_command_removed_but_others_kept(mock_gs):
    app = PDFXZApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        commands = list(app.get_system_commands(app.screen))
        titles = [c.title for c in commands]
        assert "Screenshot" not in titles
        assert "Quit" in titles
        assert "Theme" in titles
