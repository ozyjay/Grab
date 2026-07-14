from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from grab_app.application import GrabApplication


class ApplicationTests(unittest.TestCase):
    def test_shell_capture_must_be_a_runtime_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            capture = runtime / "grab-example.png"
            capture.write_bytes(b"png")

            with patch(
                "grab_app.application.GLib.get_user_runtime_dir",
                return_value=str(runtime),
            ):
                self.assertEqual(GrabApplication._validated_capture_path(capture), capture)

                outside = runtime / "other.png"
                outside.write_bytes(b"png")
                with self.assertRaises(ValueError):
                    GrabApplication._validated_capture_path(outside)


if __name__ == "__main__":
    unittest.main()
