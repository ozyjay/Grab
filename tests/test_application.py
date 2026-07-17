from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import cairo

from grab_app.annotation import (
    AnnotationDocument,
    CropRectangle,
    PendingAnnotationStore,
)
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
        self.assertEqual(arguments[:2], ("Edit", "app.annotate"))
        self.assertEqual(arguments[2].unpack(), "abc123")

    def test_unsaved_screenshot_notification_offers_save(self):
        application = GrabApplication()
        notification = MagicMock()

        with (
            patch("grab_app.application.Gio.Notification.new", return_value=notification),
            patch("grab_app.application.Gio.ThemedIcon.new"),
            patch.object(application, "send_notification"),
        ):
            application._notify("Screenshot copied", None, "abc123", offer_save=True)

        calls = notification.add_button_with_target.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["Edit", "Save"])
        self.assertEqual(calls[1].args[1], "app.save-screenshot")
        self.assertEqual(calls[1].args[2].unpack(), "abc123")

    def test_save_action_creates_copy_and_updates_pending_screenshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshots = root / "Pictures" / "Screenshots"
            source = root / "source.png"
            self.make_png(source)
            store = PendingAnnotationStore(root / "runtime", screenshots)
            pending = store.create(source, None)
            application = GrabApplication()
            application._annotations = store
            parameter = MagicMock()
            parameter.unpack.return_value = pending.token

            with (
                patch.object(
                    application, "_screenshots_directory", return_value=screenshots
                ),
                patch.object(application, "_notify") as notify,
            ):
                application._save_screenshot(MagicMock(), parameter)

            saved = list(screenshots.glob("Screenshot *.png"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_bytes(), source.read_bytes())
            self.assertEqual(store.load(pending.token).saved_path, saved[0])
            notify.assert_called_once_with(
                "Screenshot copied and saved", str(saved[0]), pending.token
            )

    def test_shell_capture_must_be_a_runtime_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            capture_directory = runtime / "grab-captures"
            capture_directory.mkdir()
            capture = capture_directory / "grab-example.png"
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

                old_location = runtime / "grab-example.png"
                old_location.write_bytes(b"png")
                with self.assertRaises(ValueError):
                    GrabApplication._validated_capture_path(old_location)

    def test_loaded_image_exposes_png_clipboard_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.png"
            self.make_png(path)

            provider = GrabApplication()._load_image(path)

            self.assertTrue(provider.ref_formats().contain_mime_type("image/png"))

    def test_set_clipboard_uses_content_provider(self):
        application = GrabApplication()
        display = MagicMock()
        clipboard = display.get_clipboard.return_value
        provider = MagicMock()

        with patch(
            "grab_app.application.Gdk.Display.get_default", return_value=display
        ):
            application._set_clipboard(provider)

        clipboard.set_content.assert_called_once_with(provider)

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
            document.apply_crop(CropRectangle(2, 1, 10, 7))
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
            rendered = cairo.ImageSurface.create_from_png(str(saved))
            self.assertEqual((rendered.get_width(), rendered.get_height()), (8, 6))
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

    def test_completed_gif_removes_source_and_notifies_with_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "grab-recording-example.webm"
            destination = root / "Screen Recording.gif"
            source.write_bytes(b"video")
            destination.write_bytes(b"gif")
            application = GrabApplication()

            with patch.object(application, "_notify") as notify:
                application._complete_gif(source, destination)

            self.assertFalse(source.exists())
            self.assertTrue(destination.exists())
            notify.assert_called_once_with("Animated GIF saved", str(destination))

    def test_cancelled_gif_removes_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "grab-recording-example.webm"
            source.write_bytes(b"video")

            GrabApplication()._cancel_gif(source)

            self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
