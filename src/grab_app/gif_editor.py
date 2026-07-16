"""GTK crop and save window for animated GIF recordings."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Callable

import cairo
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from .annotation import CropRectangle, canvas_to_image, fit_image, normalise_crop
from .config import pictures_directory
from .recording import atomic_replace, gif_command, next_recording_name


class GifCropWindow(Gtk.ApplicationWindow):
    """Preview a recording, select a crop, and encode it as an animated GIF."""

    def __init__(
        self,
        application: Gtk.Application,
        source: Path,
        completed: Callable[[Path, Path], None],
        cancelled: Callable[[Path], None],
    ) -> None:
        super().__init__(application=application)
        self.source = source
        self.completed = completed
        self.cancelled = cancelled
        self._resolved = False
        self._encoding = False
        self._temporary_output: Path | None = None
        self._process: Gio.Subprocess | None = None
        self._width = 0
        self._height = 0
        self._selection: CropRectangle | None = None
        self._drag_origin: tuple[float, float] | None = None
        self._drag_anchor = (0.0, 0.0)
        self._drag_handle: str | None = None
        self._drag_start: CropRectangle | None = None

        self.set_title("Crop GIF Recording")
        self.set_default_size(1100, 760)
        self.set_size_request(640, 420)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        layout.append(self._build_toolbar())

        self.error_label = Gtk.Label()
        self.error_label.add_css_class("error")
        self.error_label.set_margin_start(12)
        self.error_label.set_margin_end(12)
        self.error_label.set_margin_top(6)
        self.error_label.set_margin_bottom(6)
        self.error_label.set_wrap(True)
        self.error_label.set_visible(False)
        layout.append(self.error_label)

        self.media = Gtk.MediaFile.new_for_filename(str(source))
        self.media.set_loop(True)
        self.media.connect("notify::prepared", self._media_prepared)
        self.media.connect("notify::error", self._media_error)
        self.video = Gtk.Video.new_for_media_stream(self.media)
        self.video.set_autoplay(True)
        self.video.set_hexpand(True)
        self.video.set_vexpand(True)

        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        overlay.set_child(self.video)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.canvas.set_draw_func(self._draw_crop)
        gesture = Gtk.GestureDrag.new()
        gesture.set_button(Gdk.BUTTON_PRIMARY)
        gesture.connect("drag-begin", self._drag_begin)
        gesture.connect("drag-update", self._drag_update)
        gesture.connect("drag-end", self._drag_end)
        self.canvas.add_controller(gesture)
        overlay.add_overlay(self.canvas)
        layout.append(overlay)

        self.set_child(layout)
        self.connect("close-request", self._close_requested)
        if self.media.get_prepared():
            self._initialise_dimensions()

    def _build_toolbar(self) -> Gtk.Widget:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_top(10)
        toolbar.set_margin_bottom(10)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)

        title = Gtk.Label(label="Drag to choose the GIF area")
        title.add_css_class("heading")
        toolbar.append(title)
        reset = Gtk.Button(label="Reset crop")
        reset.connect("clicked", lambda *_args: self._reset_crop())
        toolbar.append(reset)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)
        self.progress = Gtk.Spinner()
        toolbar.append(self.progress)
        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", lambda *_args: self._cancel())
        toolbar.append(self.cancel_button)
        self.save_button = Gtk.Button(label="Save GIF")
        self.save_button.add_css_class("suggested-action")
        self.save_button.set_sensitive(False)
        self.save_button.connect("clicked", lambda *_args: self._choose_destination())
        toolbar.append(self.save_button)
        return toolbar

    def _media_prepared(self, _media: Gtk.MediaStream, _parameter: object) -> None:
        if self.media.get_prepared():
            self._initialise_dimensions()

    def _initialise_dimensions(self) -> None:
        self._width = self.media.get_intrinsic_width()
        self._height = self.media.get_intrinsic_height()
        if self._width <= 0 or self._height <= 0:
            self._show_error("The recording has invalid dimensions.")
            return
        if self._selection is None:
            self._selection = self._bounds()
        self.save_button.set_sensitive(not self._encoding)
        self.canvas.queue_draw()

    def _media_error(self, _media: Gtk.MediaStream, _parameter: object) -> None:
        error = self.media.get_error()
        if error is not None:
            self._show_error(f"Could not preview the recording: {error.message}")

    def _bounds(self) -> CropRectangle:
        return CropRectangle(0, 0, self._width, self._height)

    def _fit(self) -> tuple[float, float, float]:
        return fit_image(
            self._width,
            self._height,
            self.canvas.get_allocated_width(),
            self.canvas.get_allocated_height(),
        )

    def _point(
        self, x: float, y: float, clamp: bool = False
    ) -> tuple[float, float] | None:
        return canvas_to_image(
            x,
            y,
            self._width,
            self._height,
            self.canvas.get_allocated_width(),
            self.canvas.get_allocated_height(),
            clamp=clamp,
        )

    def _draw_crop(
        self, _area: Gtk.DrawingArea, context: cairo.Context, _width: int, _height: int
    ) -> None:
        selection = self._selection
        if selection is None or self._width <= 0:
            return
        scale, offset_x, offset_y = self._fit()
        context.save()
        context.translate(offset_x, offset_y)
        context.scale(scale, scale)
        context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        context.rectangle(0, 0, self._width, self._height)
        context.rectangle(
            selection.left, selection.top, selection.width, selection.height
        )
        context.set_source_rgba(0, 0, 0, 0.55)
        context.fill()
        context.rectangle(
            selection.left, selection.top, selection.width, selection.height
        )
        context.set_source_rgb(1, 1, 1)
        context.set_line_width(1.5 / scale)
        context.set_dash([6 / scale, 4 / scale])
        context.stroke()
        context.set_dash([])
        size = 8 / scale
        for x in (selection.left, selection.right):
            for y in (selection.top, selection.bottom):
                context.rectangle(x - size / 2, y - size / 2, size, size)
                context.fill()
        context.restore()

    def _drag_begin(self, _gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        point = self._point(x, y)
        self._drag_origin = (x, y) if point is not None else None
        if point is None:
            return
        self._drag_handle = self._handle_at(point)
        self._drag_start = self._selection
        if self._drag_handle == "new":
            self._drag_anchor = point

    def _handle_at(self, point: tuple[float, float]) -> str:
        selection = self._selection
        if selection is None:
            return "new"
        scale, _x, _y = self._fit()
        tolerance = 12 / scale
        horizontal = ""
        vertical = ""
        if abs(point[0] - selection.left) <= tolerance:
            horizontal = "left"
        elif abs(point[0] - selection.right) <= tolerance:
            horizontal = "right"
        if abs(point[1] - selection.top) <= tolerance:
            vertical = "top"
        elif abs(point[1] - selection.bottom) <= tolerance:
            vertical = "bottom"
        if (
            horizontal
            and selection.top - tolerance <= point[1] <= selection.bottom + tolerance
        ):
            return horizontal + (f"-{vertical}" if vertical else "")
        if (
            vertical
            and selection.left - tolerance <= point[0] <= selection.right + tolerance
        ):
            return vertical
        if (
            selection.left < point[0] < selection.right
            and selection.top < point[1] < selection.bottom
        ):
            return "move"
        return "new"

    def _drag_update(
        self, _gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        if self._drag_origin is None:
            return
        point = self._point(
            self._drag_origin[0] + offset_x,
            self._drag_origin[1] + offset_y,
            clamp=True,
        )
        if point is None:
            return
        original = self._drag_start
        handle = self._drag_handle
        if handle == "new":
            selection = normalise_crop(self._drag_anchor, point, self._bounds())
        elif handle == "move" and original is not None:
            start = self._point(*self._drag_origin, clamp=True)
            if start is None:
                return
            dx = point[0] - start[0]
            dy = point[1] - start[1]
            left = min(max(original.left + dx, 0), self._width - original.width)
            top = min(max(original.top + dy, 0), self._height - original.height)
            selection = CropRectangle(
                round(left),
                round(top),
                round(left) + original.width,
                round(top) + original.height,
            )
        elif original is not None and handle is not None:
            left = point[0] if "left" in handle else original.left
            right = point[0] if "right" in handle else original.right
            top = point[1] if "top" in handle else original.top
            bottom = point[1] if "bottom" in handle else original.bottom
            selection = normalise_crop((left, top), (right, bottom), self._bounds())
        else:
            selection = None
        if selection is not None:
            self._selection = selection
            self.save_button.set_sensitive(not self._encoding)
            self.canvas.queue_draw()

    def _drag_end(self, *_args: object) -> None:
        self._drag_origin = None
        self._drag_handle = None
        self._drag_start = None

    def _reset_crop(self) -> None:
        if self._width > 0 and not self._encoding:
            self._selection = self._bounds()
            self.canvas.queue_draw()

    def _choose_destination(self) -> None:
        if self._selection is None or self._encoding:
            return
        directory = pictures_directory() / "Screenshots"
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._show_error(f"Could not prepare the screenshots folder: {error}")
            return
        dialog = Gtk.FileDialog()
        dialog.set_title("Save Animated GIF")
        dialog.set_initial_folder(Gio.File.new_for_path(str(directory)))
        dialog.set_initial_name(next_recording_name())
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Animated GIF")
        file_filter.add_mime_type("image/gif")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)
        dialog.save(self, None, self._destination_chosen)

    def _destination_chosen(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            selected = dialog.save_finish(result)
        except GLib.Error as error:
            if not error.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                self._show_error(f"Could not choose a destination: {error.message}")
            return
        destination_value = selected.get_path()
        if not destination_value:
            self._show_error("The selected destination is not a local file.")
            return
        destination = Path(destination_value)
        if destination.suffix.lower() != ".gif":
            destination = destination.with_suffix(".gif")
        self._encode(destination)

    def _encode(self, destination: Path) -> None:
        selection = self._selection
        if selection is None:
            return
        try:
            fd, temporary = tempfile.mkstemp(
                dir=destination.parent, prefix=".grab-gif-", suffix=".gif"
            )
            os.close(fd)
            self._temporary_output = Path(temporary)
            self._process = Gio.Subprocess.new(
                gif_command(self.source, self._temporary_output, selection),
                Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_PIPE,
            )
        except Exception as error:
            self._discard_temporary()
            self._show_error(f"Could not start GIF conversion: {error}")
            return
        self._encoding = True
        self.media.pause()
        self.progress.start()
        self.save_button.set_sensitive(False)
        self.cancel_button.set_sensitive(False)
        self.error_label.set_visible(False)
        self._process.communicate_utf8_async(None, None, self._encoded, destination)

    def _encoded(
        self, process: Gio.Subprocess, result: Gio.AsyncResult, destination: Path
    ) -> None:
        try:
            _ok, _stdout, stderr = process.communicate_utf8_finish(result)
            if not process.get_successful():
                detail = (stderr or "ffmpeg exited unsuccessfully.").strip()
                raise RuntimeError(detail)
            if self._temporary_output is None:
                raise RuntimeError("The temporary GIF is unavailable.")
            atomic_replace(self._temporary_output, destination)
            self._temporary_output = None
        except Exception as error:
            self._encoding_finished()
            self._discard_temporary()
            self._show_error(f"Could not create the animated GIF: {error}")
            self.media.play()
            return
        self._encoding_finished()
        self._resolved = True
        self.completed(self.source, destination)
        self.destroy()

    def _encoding_finished(self) -> None:
        self._encoding = False
        self._process = None
        self.progress.stop()
        self.save_button.set_sensitive(self._selection is not None)
        self.cancel_button.set_sensitive(True)

    def _show_error(self, message: str) -> None:
        self.error_label.set_label(message)
        self.error_label.set_visible(True)

    def _discard_temporary(self) -> None:
        if self._temporary_output is not None:
            self._temporary_output.unlink(missing_ok=True)
            self._temporary_output = None

    def _cancel(self) -> None:
        if self._encoding:
            return
        if not self._resolved:
            self._resolved = True
            self.cancelled(self.source)
        self.destroy()

    def _close_requested(self, _window: Gtk.Window) -> bool:
        if self._encoding:
            return True
        if not self._resolved:
            self._resolved = True
            self.cancelled(self.source)
        return False
