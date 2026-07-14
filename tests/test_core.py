from pathlib import Path
import tempfile
import unittest

from grab_app.config import ConfigStore
from grab_app.core import CaptureCoordinator
from grab_app.portal import CaptureResult


class FakePortal:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def capture(self, callback):
        if self.error:
            raise self.error
        callback(self.result)


class CaptureTests(unittest.TestCase):
    def make_coordinator(self, portal, config, pictures, clipboard_already_set=False):
        self.notifications = []
        self.clipboard = []
        self.owned = []
        self.finished = 0

        def finish():
            self.finished += 1

        return CaptureCoordinator(
            portal=portal,
            config=config,
            load_image=lambda path: path.read_bytes(),
            set_clipboard=self.clipboard.append,
            notify=lambda title, body: self.notifications.append((title, body)),
            clipboard_owned=self.owned.append,
            finished=finish,
            pictures=lambda: pictures,
            clipboard_already_set=clipboard_already_set,
        )

    def test_success_copies_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "portal.png"
            source.write_bytes(b"png")
            config = ConfigStore(root / "config.json")
            coordinator = self.make_coordinator(
                FakePortal(CaptureResult("success", source.as_uri())), config, root
            )
            coordinator.capture()
            self.assertEqual(self.clipboard, [b"png"])
            self.assertEqual(self.owned, [b"png"])
            self.assertFalse(source.exists())
            self.assertEqual(self.notifications, [("Screenshot copied", None)])
            self.assertEqual(self.finished, 1)

    def test_save_copy_creates_screenshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "portal.png"
            source.write_bytes(b"png")
            config = ConfigStore(root / "config.json")
            config.set_save_copy(True)
            coordinator = self.make_coordinator(
                FakePortal(CaptureResult("success", source.as_uri())), config, root
            )
            coordinator.capture()
            saved = list((root / "Screenshots").glob("Screenshot *.png"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_bytes(), b"png")
            self.assertEqual(self.notifications[0][0], "Screenshot copied and saved")

    def test_shell_owned_clipboard_is_not_replaced_by_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "shell.png"
            source.write_bytes(b"png")
            coordinator = self.make_coordinator(
                FakePortal(CaptureResult("success", source.as_uri())),
                ConfigStore(root / "config.json"),
                root,
                clipboard_already_set=True,
            )

            coordinator.capture()

            self.assertEqual(self.clipboard, [])
            self.assertEqual(self.owned, [])
            self.assertFalse(source.exists())
            self.assertEqual(self.notifications, [("Screenshot copied", None)])

    def test_cancelled_and_portal_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for result, title in (
                (CaptureResult("cancelled"), "Screenshot cancelled"),
                (CaptureResult("error", message="denied"), "Screenshot failed"),
            ):
                coordinator = self.make_coordinator(
                    FakePortal(result), ConfigStore(root / "config.json"), root
                )
                coordinator.capture()
                self.assertEqual(self.notifications[0][0], title)
                self.assertEqual(self.finished, 1)

    def test_unavailable_portal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            coordinator = self.make_coordinator(
                FakePortal(error=RuntimeError("unavailable")),
                ConfigStore(root / "config.json"),
                root,
            )
            coordinator.capture()
            self.assertEqual(self.notifications, [("Screenshot failed", "unavailable")])
            self.assertEqual(self.finished, 1)

    def test_malformed_uri(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            coordinator = self.make_coordinator(
                FakePortal(CaptureResult("success", "https://example.test/image.png")),
                ConfigStore(root / "config.json"),
                root,
            )
            coordinator.capture()
            self.assertEqual(self.notifications[0][0], "Screenshot failed")
            self.assertEqual(self.clipboard, [])

    def test_clipboard_failure_still_cleans_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "portal.png"
            source.write_bytes(b"png")
            coordinator = self.make_coordinator(
                FakePortal(CaptureResult("success", source.as_uri())),
                ConfigStore(root / "config.json"),
                root,
            )
            coordinator.set_clipboard = lambda _image: (_ for _ in ()).throw(
                RuntimeError("clipboard unavailable")
            )
            coordinator.capture()
            self.assertFalse(source.exists())
            self.assertEqual(self.notifications[0], ("Screenshot failed", "clipboard unavailable"))

    def test_save_failure_still_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "portal.png"
            source.write_bytes(b"png")
            blocked = root / "blocked"
            blocked.write_text("not a directory", encoding="utf-8")
            config = ConfigStore(root / "config.json")
            config.set_save_copy(True)
            coordinator = self.make_coordinator(
                FakePortal(CaptureResult("success", source.as_uri())), config, blocked
            )
            coordinator.capture()
            self.assertEqual(self.clipboard, [b"png"])
            self.assertEqual(self.notifications[0][0], "Screenshot copied")
            self.assertIn("Could not save a copy", self.notifications[0][1])


if __name__ == "__main__":
    unittest.main()
