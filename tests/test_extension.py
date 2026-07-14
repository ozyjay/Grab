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

    def test_click_contract_is_present(self):
        source = (EXTENSION / "extension.js").read_text(encoding="utf-8")
        self.assertIn("Clutter.BUTTON_PRIMARY", source)
        self.assertIn("Clutter.BUTTON_SECONDARY", source)
        self.assertIn("'--preferences'", source)
        self.assertIn("Gio.Subprocess.new", source)


if __name__ == "__main__":
    unittest.main()
