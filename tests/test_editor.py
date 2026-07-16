from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from grab_app.editor import AnnotationWindow
from grab_app.annotation import CropRectangle
from grab_app.gif_editor import GifCropWindow


class EditorModeTests(unittest.TestCase):
    @staticmethod
    def make_window():
        return SimpleNamespace(
            _mode="pen",
            _crop_selection="selection",
            pen_button=MagicMock(),
            crop_button=MagicMock(),
            colour_button=MagicMock(),
            width_scale=MagicMock(),
            apply_crop_button=MagicMock(),
            cancel_crop_button=MagicMock(),
            canvas=MagicMock(),
            _update_buttons=MagicMock(),
        )

    def test_selecting_modes_keeps_exactly_one_toggle_active(self):
        window = self.make_window()

        AnnotationWindow._select_mode(window, "crop")

        self.assertEqual(window._mode, "crop")
        window.pen_button.set_active.assert_called_with(False)
        window.crop_button.set_active.assert_called_with(True)
        self.assertEqual(window._crop_selection, "selection")

        AnnotationWindow._select_mode(window, "pen")

        self.assertEqual(window._mode, "pen")
        window.pen_button.set_active.assert_called_with(True)
        window.crop_button.set_active.assert_called_with(False)
        self.assertIsNone(window._crop_selection)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            AnnotationWindow._select_mode(self.make_window(), "erase")


class GifCropTests(unittest.TestCase):
    def test_crop_hit_testing_finds_handles_move_and_new_selection(self):
        window = SimpleNamespace(
            _selection=CropRectangle(10, 10, 90, 70),
            _fit=lambda: (1.0, 0.0, 0.0),
        )
        self.assertEqual(GifCropWindow._handle_at(window, (10, 10)), "left-top")
        self.assertEqual(GifCropWindow._handle_at(window, (50, 40)), "move")
        self.assertEqual(GifCropWindow._handle_at(window, (200, 200)), "new")

    def test_moving_crop_is_clamped_to_recording(self):
        save_button = MagicMock()
        canvas = MagicMock()
        window = SimpleNamespace(
            _selection=CropRectangle(10, 10, 50, 40),
            _drag_origin=(20.0, 20.0),
            _drag_start=CropRectangle(10, 10, 50, 40),
            _drag_handle="move",
            _width=100,
            _height=80,
            _encoding=False,
            save_button=save_button,
            canvas=canvas,
            _point=lambda x, y, clamp=False: (
                min(max(x, 0), 100),
                min(max(y, 0), 80),
            ),
            _bounds=lambda: CropRectangle(0, 0, 100, 80),
        )

        GifCropWindow._drag_update(window, MagicMock(), 100, 100)

        self.assertEqual(window._selection, CropRectangle(60, 50, 100, 80))
        save_button.set_sensitive.assert_called_with(True)
        canvas.queue_draw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
