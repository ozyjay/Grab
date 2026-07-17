"""GTK application and preferences window for Grab."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile
from typing import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import APP_ID, APP_NAME
from .annotation import (
    AnnotationDocument,
    PendingAnnotation,
    PendingAnnotationStore,
    render_annotation,
    replace_saved_copy,
)
from .config import ConfigStore, next_screenshot_path, pictures_directory
from .core import CaptureCoordinator
from .editor import AnnotationWindow
from .gif_editor import GifCropWindow
from .portal import CaptureResult, ScreenshotPortal
from .recording import cleanup_recordings, validate_recording_path


class CapturedFile:
    """Adapt a screenshot created by GNOME Shell to the capture workflow."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def capture(self, callback: Callable[[CaptureResult], None]) -> None:
        callback(CaptureResult("success", uri=self.path.as_uri()))


class GrabApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.config = ConfigStore()
        self.preferences_window: Gtk.ApplicationWindow | None = None
        self._clipboard_holding = False
        self._clipboard_image: object | None = None
        self._portal: object | None = None
        self._capture_in_progress = False
        self._annotation_windows: dict[str, AnnotationWindow] = {}
        self._gif_windows: dict[Path, GifCropWindow] = {}
        self._annotations = PendingAnnotationStore(
            Path(GLib.get_user_runtime_dir()),
            self._screenshots_directory(),
        )

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        action = Gio.SimpleAction.new("preferences", None)
        action.connect("activate", lambda *_args: self.show_preferences())
        self.add_action(action)

        action = Gio.SimpleAction.new("dismiss-notification", None)
        action.connect("activate", self._dismiss_notification)
        self.add_action(action)

        action = Gio.SimpleAction.new("annotate", GLib.VariantType.new("s"))
        action.connect("activate", self._open_annotation)
        self.add_action(action)

        action = Gio.SimpleAction.new("save-screenshot", GLib.VariantType.new("s"))
        action.connect("activate", self._save_screenshot)
        self.add_action(action)
        self._annotations.cleanup()
        cleanup_recordings(Path(GLib.get_user_runtime_dir()))

    def do_activate(self) -> None:
        self.take_screenshot()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        arguments = command_line.get_arguments()[1:]
        if arguments == ["--preferences"]:
            self.activate_action("preferences", None)
            return 0
        if len(arguments) == 2 and arguments[0] == "--capture-file":
            try:
                path = self._validated_capture_path(Path(arguments[1]))
            except (OSError, ValueError) as error:
                self._notify("Screenshot failed", str(error))
                return 1
            self._begin_capture(CapturedFile(path), clipboard_already_set=True)
            return 0
        if len(arguments) == 2 and arguments[0] == "--recording-file":
            try:
                path = validate_recording_path(
                    Path(arguments[1]), Path(GLib.get_user_runtime_dir())
                )
            except (OSError, ValueError) as error:
                self._notify("Recording unavailable", str(error))
                return 1
            self._open_gif_editor(path)
            return 0
        if arguments:
            command_line.printerr("Usage: grab [--preferences]\n")
            return 2
        self.activate()
        return 0

    @staticmethod
    def _validated_capture_path(path: Path) -> Path:
        if path.is_symlink():
            raise ValueError("The screenshot file is invalid.")
        runtime_directory = Path(GLib.get_user_runtime_dir()).resolve(strict=True)
        capture_directory = runtime_directory / "grab-captures"
        if capture_directory.is_symlink():
            raise ValueError("The screenshot directory is invalid.")
        capture_directory = capture_directory.resolve(strict=True)
        if capture_directory.parent != runtime_directory:
            raise ValueError("The screenshot directory is invalid.")
        path = path.resolve(strict=True)
        if path.parent != capture_directory or not path.name.startswith("grab-"):
            raise ValueError("The screenshot file is outside Grab's runtime directory.")
        if path.suffix.lower() != ".png" or not path.is_file():
            raise ValueError("The screenshot file is invalid.")
        return path

    def _notify(
        self,
        title: str,
        body: str | None,
        annotation_token: str | None = None,
        offer_save: bool = False,
    ) -> None:
        notification = Gio.Notification.new(title)
        if body:
            notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        notification.set_default_action("app.dismiss-notification")
        if annotation_token:
            notification.add_button_with_target(
                "Edit",
                "app.annotate",
                GLib.Variant("s", annotation_token),
            )
            if offer_save:
                notification.add_button_with_target(
                    "Save",
                    "app.save-screenshot",
                    GLib.Variant("s", annotation_token),
                )
        self.send_notification("capture-status", notification)

    def _dismiss_notification(self, *_args: object) -> None:
        self.withdraw_notification("capture-status")

    def _screenshots_directory(self) -> Path:
        return pictures_directory() / "Screenshots"

    def _stage_annotation(self, source: Path, saved: Path | None) -> str:
        return self._annotations.create(source, saved).token

    def _save_screenshot(
        self, _action: Gio.SimpleAction, parameter: GLib.Variant | None
    ) -> None:
        if parameter is None:
            self._notify(
                "Could not save screenshot", "The screenshot token is missing."
            )
            return
        token = parameter.unpack()
        if not isinstance(token, str):
            self._notify(
                "Could not save screenshot", "The screenshot token is invalid."
            )
            return
        try:
            pending = self._annotations.load(token)
            if pending.saved_path is not None:
                destination = pending.saved_path
            else:
                directory = self._screenshots_directory()
                directory.mkdir(parents=True, exist_ok=True)
                destination = next_screenshot_path(directory)
                shutil.copy2(pending.image_path, destination)
                try:
                    self._annotations.set_saved_path(token, destination)
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
        except Exception as error:
            self._notify("Could not save screenshot", str(error))
            return
        self._notify("Screenshot copied and saved", str(destination), token)

    def _open_annotation(
        self, _action: Gio.SimpleAction, parameter: GLib.Variant | None
    ) -> None:
        if parameter is None:
            self._notify("Annotation unavailable", "The annotation token is missing.")
            return
        token = parameter.unpack()
        if not isinstance(token, str):
            self._notify("Annotation unavailable", "The annotation token is invalid.")
            return
        existing = self._annotation_windows.get(token)
        if existing is not None:
            existing.present()
            return
        try:
            pending = self._annotations.claim(token)
            window = AnnotationWindow(
                self,
                pending,
                self._complete_annotation,
                self._cancel_annotation,
            )
        except Exception as error:
            self._annotations.delete(token)
            self._notify("Annotation unavailable", str(error))
            return
        self.withdraw_notification("capture-status")
        window.connect("destroy", lambda *_args: self._annotation_windows.pop(token, None))
        self._annotation_windows[token] = window
        window.present()

    def _complete_annotation(
        self, pending: PendingAnnotation, document: AnnotationDocument
    ) -> str | None:
        self._annotations.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, output_name = tempfile.mkstemp(
            dir=self._annotations.directory,
            prefix=f".{pending.token}-",
            suffix=".png",
        )
        os.close(fd)
        output = Path(output_name)
        try:
            render_annotation(
                pending.image_path,
                output,
                document.all_strokes(),
                document.crop,
            )
            image = self._load_image(output)
            self._set_clipboard(image)
            self._own_clipboard(image)
        except Exception as error:
            output.unlink(missing_ok=True)
            return f"Could not copy the edited screenshot: {error}"

        save_error: Exception | None = None
        if pending.saved_path is not None:
            try:
                destination = self._annotations.validate_saved_path(pending.saved_path)
                replace_saved_copy(output, destination)
            except Exception as error:
                save_error = error
        output.unlink(missing_ok=True)
        self._annotations.delete(pending.token)
        if save_error:
            self._notify(
                "Screenshot edited",
                f"Could not replace the saved copy: {save_error}",
            )
        else:
            self._notify("Screenshot edited", None)
        return None

    def _cancel_annotation(self, pending: PendingAnnotation) -> None:
        self._annotations.delete(pending.token)

    def _open_gif_editor(self, path: Path) -> None:
        existing = self._gif_windows.get(path)
        if existing is not None:
            existing.present()
            return
        try:
            window = GifCropWindow(
                self,
                path,
                self._complete_gif,
                self._cancel_gif,
            )
        except Exception as error:
            path.unlink(missing_ok=True)
            self._notify("Recording unavailable", str(error))
            return
        window.connect("destroy", lambda *_args: self._gif_windows.pop(path, None))
        self._gif_windows[path] = window
        window.present()

    def _complete_gif(self, source: Path, destination: Path) -> None:
        source.unlink(missing_ok=True)
        self._notify("Animated GIF saved", str(destination))

    def _cancel_gif(self, source: Path) -> None:
        source.unlink(missing_ok=True)

    def _load_image(self, path: Path) -> Gdk.ContentProvider:
        png = GLib.Bytes.new(path.read_bytes())
        return Gdk.ContentProvider.new_for_bytes("image/png", png)

    def _set_clipboard(self, image: object) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("No graphical display is available.")
        display.get_clipboard().set_content(image)

    def _own_clipboard(self, image: object) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("No graphical display is available.")
        clipboard = display.get_clipboard()
        self._clipboard_image = image
        if not self._clipboard_holding:
            self._clipboard_holding = True
            self.hold()
            clipboard.connect("changed", self._on_clipboard_changed)

    def _on_clipboard_changed(self, clipboard: Gdk.Clipboard) -> None:
        if self._clipboard_holding and not clipboard.is_local():
            self._clipboard_holding = False
            self._clipboard_image = None
            self.release()

    def take_screenshot(self) -> None:
        try:
            portal = ScreenshotPortal()
        except Exception as error:
            self._notify("Screenshot failed", str(error))
            return
        self._begin_capture(portal)

    def _begin_capture(self, portal: object, clipboard_already_set: bool = False) -> None:
        if self._capture_in_progress:
            self._notify("Screenshot already in progress", None)
            return
        self._capture_in_progress = True
        self.hold()
        try:
            self._portal = portal
            coordinator = CaptureCoordinator(
                portal=self._portal,
                config=self.config,
                load_image=self._load_image,
                set_clipboard=self._set_clipboard,
                notify=self._notify,
                clipboard_owned=self._own_clipboard,
                finished=self._capture_finished,
                stage_annotation=self._stage_annotation,
                clipboard_already_set=clipboard_already_set,
            )
            coordinator.capture()
        except Exception as error:
            self._notify("Screenshot failed", str(error))
            self._capture_finished()

    def _capture_finished(self) -> None:
        if self._capture_in_progress:
            self._capture_in_progress = False
            self.release()

    def show_preferences(self) -> None:
        if self.preferences_window is not None:
            self.preferences_window.present()
            return

        window = Gtk.ApplicationWindow(application=self)
        window.set_title(f"{APP_NAME} Preferences")
        window.set_default_size(440, 140)
        window.set_resizable(False)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        row.set_margin_top(28)
        row.set_margin_bottom(28)
        row.set_margin_start(28)
        row.set_margin_end(28)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text.set_hexpand(True)
        title = Gtk.Label(label="Save screenshots automatically")
        title.set_xalign(0)
        title.add_css_class("heading")
        description = Gtk.Label(
            label=(
                "Permanent copies go to Pictures/Screenshots. "
                "Temporary editing copies are kept for up to 24 hours."
            )
        )
        description.set_xalign(0)
        description.set_wrap(True)
        description.add_css_class("dim-label")
        text.append(title)
        text.append(description)

        toggle = Gtk.Switch()
        toggle.set_valign(Gtk.Align.CENTER)
        toggle.set_active(self.config.load()["save_copy"])
        toggle.connect("notify::active", self._save_preference)
        row.append(text)
        row.append(toggle)
        window.set_child(row)
        window.connect("destroy", self._preferences_destroyed)
        self.preferences_window = window
        window.present()

    def _save_preference(self, toggle: Gtk.Switch, _parameter: object) -> None:
        try:
            self.config.set_save_copy(toggle.get_active())
        except OSError as error:
            self._notify("Could not save preferences", str(error))

    def _preferences_destroyed(self, _window: Gtk.Window) -> None:
        self.preferences_window = None


def main() -> int:
    return GrabApplication().run(sys.argv)
