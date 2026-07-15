from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import cairo

from grab_app.annotation import AnnotationDocument, PendingAnnotationStore
from grab_app.application import GrabApplication


class ApplicationTests(unittest.TestCase):
    @staticmethod
    def make_png(path, width=12, height=8):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        context = cairo.Context(surface)
        context.set_source_rgb(1, 1, 1)
        context.paint()
        surface.write_to_png(str(path))

    def test_notification_click_uses_dismiss_action(self):
        application = GrabApplication()
        notification = MagicMock()

        with (
            patch("grab_app.application.Gio.Notification.new", return_value=notification),
            patch("grab_app.application.Gio.ThemedIcon.new"),
            patch.object(application, "send_notification"),
        ):
            application._notify("Screenshot copied", None)

        notification.set_default_action.assert_called_once_with(
            "app.dismiss-notification"
        )

    def test_success_notification_offers_annotation(self):
        application = GrabApplication()
        notification = MagicMock()

        with (
            patch("grab_app.application.Gio.Notification.new", return_value=notification),
            patch("grab_app.application.Gio.ThemedIcon.new"),
            patch.object(application, "send_notification"),
        ):
            application._notify("Screenshot copied", None, "abc123")

        arguments = notification.add_button_with_target.call_args.args
        self.assertEqual(arguments[:2], ("Annotate", "app.annotate"))
        self.assertEqual(arguments[2].unpack(), "abc123")

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

    def test_annotation_completion_replaces_clipboard_and_saved_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshots = root / "Pictures" / "Screenshots"
            screenshots.mkdir(parents=True)
            source = root / "source.png"
            saved = screenshots / "Screenshot example.png"
            self.make_png(source)
            self.make_png(saved)
            original = saved.read_bytes()
            store = PendingAnnotationStore(root / "runtime", screenshots)
            pending = store.create(source, saved)
            document = AnnotationDocument(12, 8)
            document.begin_stroke((1, 4), (1, 0, 0, 1), 3)
            document.append_point((11, 4))
            document.end_stroke()
            application = GrabApplication()
            application._annotations = store

            with (
                patch.object(application, "_load_image", return_value="texture"),
                patch.object(application, "_set_clipboard") as set_clipboard,
                patch.object(application, "_own_clipboard") as own_clipboard,
                patch.object(application, "_notify"),
            ):
                error = application._complete_annotation(pending, document)

            self.assertIsNone(error)
            set_clipboard.assert_called_once_with("texture")
            own_clipboard.assert_called_once_with("texture")
            self.assertNotEqual(saved.read_bytes(), original)
            self.assertFalse(pending.image_path.exists())

    def test_clipboard_failure_keeps_pending_annotation_and_saved_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshots = root / "Pictures" / "Screenshots"
            screenshots.mkdir(parents=True)
            source = root / "source.png"
            saved = screenshots / "Screenshot example.png"
            self.make_png(source)
            self.make_png(saved)
            original = saved.read_bytes()
            store = PendingAnnotationStore(root / "runtime", screenshots)
            pending = store.create(source, saved)
            application = GrabApplication()
            application._annotations = store

            with (
                patch.object(application, "_load_image", return_value="texture"),
                patch.object(
                    application,
                    "_set_clipboard",
                    side_effect=RuntimeError("clipboard unavailable"),
                ),
            ):
                error = application._complete_annotation(
                    pending, AnnotationDocument(12, 8)
                )

            self.assertIn("clipboard unavailable", error)
            self.assertEqual(saved.read_bytes(), original)
            self.assertTrue(pending.image_path.exists())

    def test_saved_copy_failure_preserves_original_and_finishes_clipboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshots = root / "Pictures" / "Screenshots"
            screenshots.mkdir(parents=True)
            source = root / "source.png"
            saved = screenshots / "Screenshot example.png"
            self.make_png(source)
            self.make_png(saved)
            original = saved.read_bytes()
            store = PendingAnnotationStore(root / "runtime", screenshots)
            pending = store.create(source, saved)
            application = GrabApplication()
            application._annotations = store

            with (
                patch.object(application, "_load_image", return_value="texture"),
                patch.object(application, "_set_clipboard"),
                patch.object(application, "_own_clipboard"),
                patch.object(application, "_notify") as notify,
                patch(
                    "grab_app.application.replace_saved_copy",
                    side_effect=OSError("read-only"),
                ),
            ):
                error = application._complete_annotation(
                    pending, AnnotationDocument(12, 8)
                )

            self.assertIsNone(error)
            self.assertEqual(saved.read_bytes(), original)
            self.assertFalse(pending.image_path.exists())
            self.assertIn("Could not replace", notify.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
