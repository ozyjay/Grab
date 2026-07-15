from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from grab_app.editor import AnnotationWindow


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


if __name__ == "__main__":
    unittest.main()
