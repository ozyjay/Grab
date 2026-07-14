"""GTK application and preferences window for Grab."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import APP_ID, APP_NAME
from .config import ConfigStore
from .core import CaptureCoordinator
from .portal import CaptureResult, ScreenshotPortal


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

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        action = Gio.SimpleAction.new("preferences", None)
        action.connect("activate", lambda *_args: self.show_preferences())
        self.add_action(action)

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
        if arguments:
            command_line.printerr("Usage: grab [--preferences]\n")
            return 2
        self.activate()
        return 0

    @staticmethod
    def _validated_capture_path(path: Path) -> Path:
        path = path.resolve(strict=True)
        runtime_directory = Path(GLib.get_user_runtime_dir()).resolve(strict=True)
        if path.parent != runtime_directory or not path.name.startswith("grab-"):
            raise ValueError("The screenshot file is outside Grab's runtime directory.")
        if path.suffix.lower() != ".png" or not path.is_file():
            raise ValueError("The screenshot file is invalid.")
        return path

    def _notify(self, title: str, body: str | None) -> None:
        notification = Gio.Notification.new(title)
        if body:
            notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_ID))
        self.send_notification("capture-status", notification)

    def _load_image(self, path: Path) -> Gdk.Texture:
        return Gdk.Texture.new_from_filename(str(path))

    def _set_clipboard(self, image: object) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("No graphical display is available.")
        display.get_clipboard().set(image)

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
        title = Gtk.Label(label="Save a copy")
        title.set_xalign(0)
        title.add_css_class("heading")
        description = Gtk.Label(label="Keep screenshots in Pictures/Screenshots")
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
