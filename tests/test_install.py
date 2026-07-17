from pathlib import Path
import os
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_installer_contains_safe_extension_refresh(self):
        source = (PROJECT / "install.sh").read_text(encoding="utf-8")
        info = source.index('gnome-extensions info "$EXTENSION_UUID"')
        disable = source.index('gnome-extensions disable "$EXTENSION_UUID"')
        enable = source.index('gnome-extensions enable "$EXTENSION_UUID"')
        self.assertLess(info, disable)
        self.assertLess(disable, enable)
        self.assertIn('State: ERROR', source)

    def test_installer_checks_annotation_dependency(self):
        source = (PROJECT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('python3 -c "import cairo"', source)
        self.assertIn("python3-cairo", source)

    def test_installer_checks_gif_dependencies(self):
        source = (PROJECT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("command -v ffmpeg", source)
        self.assertIn("ffmpeg-free", source)
        self.assertIn("gst-inspect-1.0 vp8dec", source)
        self.assertIn("gstreamer1-plugins-good", source)

    def test_install_and_uninstall_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(root / "home"),
                    "XDG_DATA_HOME": str(root / "data"),
                    "XDG_BIN_HOME": str(root / "bin"),
                    "GRAB_SKIP_EXTENSION_ENABLE": "1",
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
            service = root / "data/dbus-1/services/org.grabtool.Grab.service"
            launcher = root / "bin/grab"
            self.assertTrue(desktop.is_file())
            self.assertTrue(service.is_file())
            self.assertTrue(launcher.is_symlink())
            self.assertIn(f'Exec="{launcher}"', desktop.read_text(encoding="utf-8"))
            self.assertIn("NoDisplay=true", desktop.read_text(encoding="utf-8"))
            self.assertIn("DBusActivatable=true", desktop.read_text(encoding="utf-8"))
            self.assertIn(
                f'Exec="{launcher}" --gapplication-service',
                service.read_text(encoding="utf-8"),
            )
            extension = root / "data/gnome-shell/extensions/grab@grabtool.org"
            self.assertTrue((extension / "extension.js").is_file())
            self.assertTrue((extension / "duration.js").is_file())
            self.assertTrue((extension / "metadata.json").is_file())
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
            self.assertFalse(service.exists())
            self.assertFalse(launcher.exists())
            self.assertFalse(extension.exists())
            self.assertTrue(config.exists())


if __name__ == "__main__":
    unittest.main()
