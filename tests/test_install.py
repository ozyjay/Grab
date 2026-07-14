from pathlib import Path
import os
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_install_and_uninstall_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(root / "home"),
                    "XDG_DATA_HOME": str(root / "data"),
                    "XDG_BIN_HOME": str(root / "bin"),
                }
            )
            for _ in range(2):
                subprocess.run(
                    [str(PROJECT / "install.sh")],
                    cwd=PROJECT,
                    env=env,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            desktop = root / "data/applications/org.grabtool.Grab.desktop"
            launcher = root / "bin/grab"
            self.assertTrue(desktop.is_file())
            self.assertTrue(launcher.is_symlink())
            self.assertIn(f'Exec="{launcher}"', desktop.read_text(encoding="utf-8"))
            validator = subprocess.run(
                ["desktop-file-validate", str(desktop)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(validator.returncode, 0, validator.stderr)

            config = root / "home/.config/grab/settings.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"save_copy": true}\n', encoding="utf-8")
            for _ in range(2):
                subprocess.run(
                    [str(PROJECT / "uninstall.sh")],
                    cwd=PROJECT,
                    env=env,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            self.assertFalse(desktop.exists())
            self.assertFalse(launcher.exists())
            self.assertTrue(config.exists())


if __name__ == "__main__":
    unittest.main()
