from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grab_app.config import ConfigStore, next_screenshot_path, pictures_directory


class ConfigTests(unittest.TestCase):
    def test_missing_config_uses_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ConfigStore(Path(temporary) / "settings.json")
            self.assertEqual(store.load(), {"save_copy": False})

    def test_invalid_config_uses_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(ConfigStore(path).load(), {"save_copy": False})
            path.write_text(json.dumps({"save_copy": "yes"}), encoding="utf-8")
            self.assertEqual(ConfigStore(path).load(), {"save_copy": False})

    def test_setting_is_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ConfigStore(Path(temporary) / "nested" / "settings.json")
            store.set_save_copy(True)
            self.assertEqual(store.load(), {"save_copy": True})

    def test_filename_collision_adds_suffix(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            moment = datetime(2026, 7, 14, 9, 8, 7)
            first = directory / "Screenshot 2026-07-14 09-08-07.png"
            first.touch()
            second = directory / "Screenshot 2026-07-14 09-08-07 (2).png"
            second.touch()
            self.assertEqual(
                next_screenshot_path(directory, moment),
                directory / "Screenshot 2026-07-14 09-08-07 (3).png",
            )

    def test_pictures_falls_back_to_home(self):
        with patch("grab_app.config.Path.home", return_value=Path("/fake/home")):
            with patch("gi.repository.GLib.get_user_special_dir", return_value=None):
                self.assertEqual(pictures_directory(), Path("/fake/home/Pictures"))


if __name__ == "__main__":
    unittest.main()
