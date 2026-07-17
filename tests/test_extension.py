import json
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
EXTENSION = PROJECT / "extension"


class ExtensionTests(unittest.TestCase):
    def test_metadata_targets_supported_fedora_shells(self):
        metadata = json.loads((EXTENSION / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["uuid"], "grab@grabtool.org")
        self.assertEqual(metadata["shell-version"], ["48", "49", "50"])

    def test_extension_bundle_is_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    "gnome-extensions",
                    "pack",
                    str(EXTENSION),
                    "--force",
                    "--out-dir",
                    temporary,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(temporary) / "grab@grabtool.org.shell-extension.zip").is_file())

    def test_capture_and_recording_contract_is_present(self):
        source = (EXTENSION / "extension.js").read_text(encoding="utf-8")
        duration = (EXTENSION / "duration.js").read_text(encoding="utf-8")
        self.assertIn("_init(helperPath)", source)
        self.assertIn("super._init(0.0, 'Grab', false)", source)
        self.assertIn("'Take Screenshot'", source)
        self.assertIn("'button-press-event'", source)
        self.assertIn("button === Clutter.BUTTON_MIDDLE", source)
        self.assertIn("this._startRecording(DEFAULT_RECORDING_DURATION)", source)
        self.assertIn("button === Clutter.BUTTON_SECONDARY", source)
        self.assertIn("return Clutter.EVENT_STOP;", source)
        self.assertIn("'Record GIF'", source)
        self.assertIn("'How to Use Grab'", source)
        self.assertIn("'How to use Grab'", source)
        self.assertIn("'Left-click opens this menu.", source)
        self.assertIn("'Custom Duration…'", source)
        self.assertIn("MIN_CUSTOM_DURATION = 1", duration)
        self.assertIn("MAX_CUSTOM_DURATION = 300", duration)
        self.assertIn("'StopScreencast'", source)
        self.assertIn("`${pathStem}.mp4`", source)
        self.assertIn("`${pathStem}.webm`", source)
        self.assertIn("_stopFailedRecording", source)
        self.assertIn("new Shell.Screenshot()", source)
        self.assertIn("'grab-captures'", source)
        self.assertIn("GLib.mkdir_with_parents(captureDirectory, 0o700)", source)
        self.assertIn("this.menu.close()", source)
        self.assertIn("CAPTURE_DELAY_MS", source)
        self.assertLess(
            source.index("this.menu.close()"), source.index("this._takeScreenshot()")
        )
        self.assertIn("St.Clipboard.get_default().set_content", source)
        self.assertIn("'--capture-file'", source)
        self.assertIn("'--recording-file'", source)
        self.assertIn("Gio.Subprocess.new", source)

    def test_screencast_proxy_does_not_block_shell_startup(self):
        source = (EXTENSION / "extension.js").read_text(encoding="utf-8")
        self.assertIn("Gio.DBusProxy.new_for_bus(", source)
        self.assertNotIn("Gio.DBusProxy.new_for_bus_sync(", source)

    def test_custom_duration_boundaries(self):
        result = subprocess.run(
            ["gjs", "-m", str(PROJECT / "tests" / "test_duration.js")],
            cwd=PROJECT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
